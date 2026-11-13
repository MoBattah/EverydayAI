#!/usr/bin/env python3
"""agent-continuity: reconstruct the working state of a repository, read-only.

A coding agent that opens a repository after other agents have worked in it spends its
first calls rediscovering the same facts: where HEAD is, what is dirty, which branches
hold unmerged work, what landed upstream, which pull requests are open. This command
answers those questions once, in one call, and never writes to the repository.

It reports:

  1. The remote, the resolved default branch, HEAD and the dirty count.
  2. Every worktree, with a verdict: dirty, stale, abandoned, active or missing.
  3. Local branches unmerged into the default branch, and branches holding unpushed work.
  4. Commits on the default branch that the local HEAD does not contain.
  5. Open pull requests and their check state, where the remote is GitHub and gh is present.
  6. The newest checkpoint under a directory you name.
  7. The output of an optional task provider command.

Everything it runs is read-only. It never fetches, writes a ref, touches the index or
modifies a worktree. Git runs with GIT_OPTIONAL_LOCKS=0 so even `git status` cannot
refresh the index. Sections that cannot be answered are reported as unavailable and the
rest still prints.

Usage:
  agent_continuity.py                      the current repository
  agent_continuity.py --repo PATH          a named repository
  agent_continuity.py --full               no truncation of long lists
  agent_continuity.py --no-net             skip the GitHub calls
  agent_continuity.py --checkpoints DIR    newest checkpoint under DIR
  agent_continuity.py --tasks-cmd CMD      print the output of a task provider
  agent_continuity.py --json               machine-readable report

Exit status is 0 when the report is printed, 1 when the path is not a git repository or
does not exist, and 2 on a usage error. A section that cannot be answered is reported as
unavailable; the rest of the report still prints.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

STALE_DAYS = 14

MAX_WORKTREES = 12
MAX_BRANCHES = 12
MAX_COMMITS = 10
MAX_PRS = 10
MAX_TASK_LINES = 16

GIT_TIMEOUT = 15
NET_TIMEOUT = 8
TASK_TIMEOUT = 15

CHECKPOINT_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}).*\.md$")


# --------------------------------------------------------------------------- shell


def run(args, cwd=None, timeout=GIT_TIMEOUT, want_err=False):
    """Run a command and return (ok, stdout), or (ok, stdout, stderr) with want_err.

    Never raises and never writes. A tool that hangs a session opening is worse than one
    that reports a section as unavailable, so everything carries a timeout.
    """
    env = {
        **os.environ,
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
        # Even a read-only status call can refresh the index. This forbids it.
        "GIT_OPTIONAL_LOCKS": "0",
    }
    try:
        p = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return (False, "", str(exc)) if want_err else (False, "")
    if want_err:
        return p.returncode == 0, p.stdout.strip(), p.stderr.strip()
    return p.returncode == 0, p.stdout.strip()


def git(cwd, *args, timeout=GIT_TIMEOUT):
    return run(["git", *args], cwd=cwd, timeout=timeout)


# --------------------------------------------------------------------------- repo basics


def repo_root(path):
    ok, out = git(path, "rev-parse", "--show-toplevel")
    return out if ok and out else None


def default_branch(root):
    """Resolve the default branch. Never assume main.

    Order: the symbolic ref origin/HEAD, which is authoritative when set; then the first
    conventional name that exists as a remote ref; then the current branch, which at
    least lets the rest of the report render. The source is returned so a guess is
    visible as a guess.
    """
    ok, out = git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if ok and out.startswith("origin/"):
        return out[len("origin/"):], "origin/HEAD"
    for name in ("main", "master", "dev", "develop", "trunk"):
        ok, _ = git(root, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}")
        if ok:
            return name, "guessed from remote refs"
    ok, out = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return (out or "HEAD"), "fell back to the current branch"


def default_ref(root, branch):
    """Prefer the remote-tracking ref: a local default branch is often behind."""
    ok, _ = git(root, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}")
    return f"origin/{branch}" if ok else branch


def remote_url(root):
    ok, out = git(root, "remote", "get-url", "origin")
    return out if ok else ""


def github_slug(url):
    """owner/repo for a github.com remote, else None.

    Handles https, ssh://git@host/path and scp-style git@host:path. A host alias such as
    github-work is accepted because it is a common ~/.ssh/config entry for github.com.
    """
    if not url:
        return None
    u = url.strip()
    if u.endswith(".git"):
        u = u[: -len(".git")]

    if u.startswith(("https://", "http://")):
        rest = u.split("://", 1)[1]
        host, _, path = rest.partition("/")
        if host != "github.com" and not host.startswith("www.github.com"):
            return None
    elif u.startswith("ssh://"):
        rest = u[len("ssh://"):]
        if "@" in rest:
            rest = rest.split("@", 1)[1]
        host, _, path = rest.partition("/")
        if "github" not in host:
            return None
    elif u.startswith("git@"):
        rest = u[len("git@"):]
        host, _, path = rest.partition(":")
        if "github" not in host:
            return None
    else:
        return None

    parts = [p for p in path.split("/") if p]
    return "/".join(parts[:2]) if len(parts) >= 2 else None


def age_days(epoch):
    try:
        then = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    except (TypeError, ValueError):
        return None
    return (datetime.now(timezone.utc) - then).days


def plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


# --------------------------------------------------------------------------- worktrees


def list_worktrees(root):
    ok, out = git(root, "worktree", "list", "--porcelain")
    if not ok:
        return []
    trees, cur = [], {}
    for line in out.splitlines():
        if not line.strip():
            if cur:
                trees.append(cur)
                cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            if cur:
                trees.append(cur)
            cur = {"path": val, "locked": False, "detached": False}
        elif key == "branch":
            cur["branch"] = val.replace("refs/heads/", "")
        elif key == "HEAD":
            cur["head"] = val
        elif key == "detached":
            cur["detached"] = True
        elif key == "locked":
            cur["locked"] = True
    if cur:
        trees.append(cur)
    return trees


def inspect_worktree(wt, root, dref):
    """Per-worktree facts. Runs in a thread; every call is local and read-only."""
    path = wt["path"]
    info = dict(wt)
    info["exists"] = Path(path).is_dir()
    if not info["exists"]:
        info["note"] = "path is missing on disk"
        return info

    ok, out = git(path, "status", "--porcelain")
    info["dirty"] = len(out.splitlines()) if ok and out else 0

    ok, out = git(path, "log", "-1", "--format=%ct%x09%an%x09%s")
    if ok and out:
        ts, _, rest = out.partition("\t")
        author, _, subject = rest.partition("\t")
        info["age"] = age_days(ts)
        info["author"] = author
        info["subject"] = subject

    ref = wt.get("branch") or wt.get("head") or "HEAD"
    ok, out = git(root, "rev-list", "--left-right", "--count", f"{dref}...{ref}")
    if ok and out:
        parts = out.split()
        if len(parts) == 2:
            info["behind"], info["ahead"] = int(parts[0]), int(parts[1])
    return info


def worktree_verdict(info, stale_days, primary=False):
    """Label a worktree. The heuristic is stated so a reader can discount it.

    clean:     the primary checkout: dirty or not, it is not something to remove.
    abandoned: clean tree and nothing the default branch does not already have, so
               removing it loses no work.
    stale:     clean tree, unmerged commits, and no commit in stale_days.
    """
    if not info.get("exists"):
        return "missing"
    if info.get("dirty", 0):
        return "dirty"
    if primary:
        return "clean"
    ahead = info.get("ahead")
    age = info.get("age")
    if ahead == 0:
        return "abandoned"
    if age is not None and age >= stale_days:
        return "stale"
    return "active"


# --------------------------------------------------------------------------- branches


def branch_state(root, dref):
    """Local branches only.

    Remote branches are excluded on purpose: a large repository can carry hundreds, and
    a listing that long answers nothing about what this checkout is in the middle of.
    """
    unmerged = []
    ok, out = git(root, "branch", "--no-merged", dref, "--format=%(refname:short)")
    if ok and out:
        unmerged = [b for b in out.splitlines() if b.strip()]

    remote_unmerged = 0
    ok, out = git(root, "branch", "-r", "--no-merged", dref, "--format=%(refname:short)")
    if ok and out:
        remote_unmerged = len([b for b in out.splitlines() if b.strip() and "->" not in b])

    unmerged_set = set(unmerged)
    unpushed = []
    ok, out = git(
        root,
        "for-each-ref",
        "refs/heads",
        "--format=%(refname:short)%09%(upstream:short)%09%(upstream:track)",
    )
    if ok and out:
        for line in out.splitlines():
            name, _, rest = line.partition("\t")
            upstream, _, track = rest.partition("\t")
            if not upstream:
                # A branch with no upstream whose commits are all on the default ref
                # holds nothing unpushed. Without this filter the section fills with
                # merged worktree leftovers and stops being read.
                if name in unmerged_set:
                    unpushed.append({"name": name, "why": "no upstream, holds unmerged commits"})
            elif "ahead" in track:
                unpushed.append({"name": name, "why": track.strip("[]")})
    return unmerged, unpushed, remote_unmerged


def landed_since_head(root, dref, max_n):
    """Commits on the default branch that the local HEAD does not contain.

    Reported by committer, which is what git records. Git does not store who pushed a
    commit, so this does not claim to.
    """
    ok, out = git(
        root,
        "log",
        "--no-merges",
        f"HEAD..{dref}",
        f"--max-count={max_n + 1}",
        "--format=%h%x09%cr%x09%cn%x09%s",
    )
    if not ok or not out:
        return [], 0
    rows = [line.split("\t", 3) for line in out.splitlines()]
    ok2, cnt = git(root, "rev-list", "--count", f"HEAD..{dref}")
    total = int(cnt) if ok2 and cnt.isdigit() else len(rows)
    return rows[:max_n], total


# --------------------------------------------------------------------------- pull requests


def open_prs(root, slug, max_n):
    """Open PRs via gh. Returns (rows, note). Degrades quietly and says why."""
    if not slug:
        return None, "the remote is not GitHub, so pull requests were not checked"
    if not shutil.which("gh"):
        return None, "gh is not installed, so pull requests were not checked"
    ok, out, err = run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            slug,
            "--state",
            "open",
            "--limit",
            str(max_n),
            "--json",
            "number,title,headRefName,author,isDraft,statusCheckRollup",
        ],
        cwd=root,
        timeout=NET_TIMEOUT,
        want_err=True,
    )
    if not ok or not out:
        why = (err.splitlines() or ["gh returned nothing"])[0][:140]
        return None, f"gh said: {why}"
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None, "gh returned output that did not parse as JSON"
    rows = []
    for pr in data:
        checks = pr.get("statusCheckRollup") or []
        states = [c.get("conclusion") or c.get("status") or c.get("state") or "" for c in checks]
        if not states:
            ci = "no checks"
        elif any(s in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED") for s in states):
            ci = "failing"
        elif any(s in ("PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED") for s in states):
            ci = "running"
        elif all(s in ("SUCCESS", "NEUTRAL", "SKIPPED") for s in states):
            ci = "passing"
        else:
            ci = "mixed"
        rows.append(
            {
                "number": pr.get("number"),
                "title": pr.get("title", ""),
                "branch": pr.get("headRefName", ""),
                "author": (pr.get("author") or {}).get("login", ""),
                "draft": pr.get("isDraft", False),
                "ci": ci,
            }
        )
    return rows, None


# --------------------------------------------------------------------------- checkpoints


def newest_checkpoint(folder):
    """The newest checkpoint under a folder, by its YYYY-MM-DD file name.

    File name and never mtime for ordering: a clone stamps every file with the same
    time, and the newest by mtime is then whichever the filesystem lists first. Age is
    computed from the date in the name, with mtime as a fallback.
    """
    if folder is None or not Path(folder).is_dir():
        return None
    best = None
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
        if Path(root).name != "checkpoints":
            continue
        for f in files:
            if CHECKPOINT_RE.match(f) and (best is None or f > best.name):
                best = Path(root) / f
    if best is None:
        return None

    focus = ""
    try:
        with open(best, encoding="utf-8", errors="replace") as fh:
            for _, line in zip(range(12), fh):
                m = re.match(r"\*\*Session focus:\*\*\s*(.+)", line, re.I)
                if m:
                    focus = m.group(1).strip()
                    break
    except OSError:
        pass

    m = CHECKPOINT_RE.match(best.name)
    days = None
    if m:
        try:
            days = (date.today() - date.fromisoformat(m.group(1))).days
        except ValueError:
            days = None
    if days is None:
        try:
            days = (time.time() - best.stat().st_mtime) / 86400.0
        except OSError:
            days = None
    return {"path": str(best), "age_days": days, "focus": focus}


# --------------------------------------------------------------------------- tasks


def task_output(command, root, max_lines):
    """Run an optional task provider and return (lines, total, note).

    The contract is one line per task on stdout, exit 0. A provider that fails is
    reported as unavailable rather than treated as an empty list, because an empty
    list reads as "nothing owed".
    """
    if not command:
        return None, 0, "no task provider was configured"
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return None, 0, f"the task command is not parseable: {exc}"
    if not argv:
        return None, 0, "the task command is empty"
    ok, out, err = run(argv, cwd=root, timeout=TASK_TIMEOUT, want_err=True)
    if not ok:
        why = (err.splitlines() or ["the command printed nothing"])[0][:160]
        return None, 0, f"the task provider failed: {why}"
    lines = out.splitlines() if out else []
    return lines[:max_lines], len(lines), None


# --------------------------------------------------------------------------- collect


def collect(root, args):
    dbranch, dsource = default_branch(root)
    dref = default_ref(root, dbranch)
    url = remote_url(root)
    slug = github_slug(url)

    _, cur = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    _, head = git(root, "rev-parse", "--short", "HEAD")
    ok, st = git(root, "status", "--porcelain")
    dirty = len(st.splitlines()) if ok and st else 0

    trees = list_worktrees(root)
    if trees:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            infos = list(pool.map(lambda w: inspect_worktree(w, root, dref), trees))
    else:
        infos = []
    for idx, info in enumerate(infos):
        info["primary"] = idx == 0
        info["verdict"] = worktree_verdict(info, args.stale_days, primary=info["primary"])

    unmerged, unpushed, remote_unmerged = branch_state(root, dref)
    landed_rows, landed_total = landed_since_head(
        root, dref, MAX_COMMITS if not args.full else 200
    )

    if args.no_net:
        prs = {"status": "skipped", "reason": "--no-net", "items": []}
    else:
        found, note = open_prs(root, slug, MAX_PRS if not args.full else 100)
        prs = (
            {"status": "unavailable", "reason": note, "items": []}
            if found is None
            else {"status": "ok", "reason": None, "items": found}
        )

    checkpoints = {"status": "skipped", "dir": args.checkpoints, "newest": None}
    if args.checkpoints:
        folder = Path(args.checkpoints)
        if not folder.is_absolute():
            folder = Path(root) / folder
        if not folder.is_dir():
            checkpoints = {"status": "missing", "dir": str(folder), "newest": None}
        else:
            cp = newest_checkpoint(folder)
            checkpoints = {
                "status": "ok" if cp else "none",
                "dir": str(folder),
                "newest": cp,
            }

    if args.no_tasks:
        tasks = {"status": "skipped", "command": args.tasks_cmd, "reason": "--no-tasks",
                 "lines": [], "total": 0}
    elif not args.tasks_cmd:
        tasks = {"status": "skipped", "command": None, "reason": "no --tasks-cmd was given",
                 "lines": [], "total": 0}
    else:
        task_lines, task_total, note = task_output(
            args.tasks_cmd, root, MAX_TASK_LINES if not args.full else 10**6
        )
        tasks = (
            {"status": "unavailable", "command": args.tasks_cmd, "reason": note,
             "lines": [], "total": 0}
            if task_lines is None
            else {"status": "ok", "command": args.tasks_cmd, "reason": None,
                  "lines": task_lines, "total": task_total}
        )

    return {
        "repo": root,
        "remote": url or None,
        "github": slug,
        "default_branch": {"name": dbranch, "source": dsource, "ref": dref},
        "head": {"branch": cur or None, "sha": head or None, "dirty": dirty},
        "worktrees": infos,
        "branches": {
            "unmerged": unmerged,
            "unpushed": unpushed,
            "remote_only_unmerged": remote_unmerged,
        },
        "landed": {"commits": landed_rows, "total": landed_total},
        "pull_requests": prs,
        "checkpoints": checkpoints,
        "tasks": tasks,
    }


# --------------------------------------------------------------------------- render


def header(title):
    return f"\n{title}\n{'-' * len(title)}"


def render_text(data, args):
    lines = []
    lines.append(f"agent-continuity · {data['repo']}")
    lines.append(f"remote {data['remote'] or 'none'}")
    db = data["default_branch"]
    lines.append(f"default branch {db['name']} ({db['source']}), comparing against {db['ref']}")
    hd = data["head"]
    lines.append(
        f"HEAD {hd['sha']} on {hd['branch']}, "
        + (f"{plural(hd['dirty'], 'uncommitted change')}" if hd["dirty"] else "tree clean")
    )

    infos = data["worktrees"]
    counts = {}
    for info in infos:
        counts[info["verdict"]] = counts.get(info["verdict"], 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items())) or "none"
    lines.append(header(f"Worktrees ({len(infos)}): {summary}"))
    lines.append(
        "  dirty = uncommitted changes."
        f" stale = clean, unmerged, no commit in {args.stale_days} days."
    )
    lines.append("  abandoned = clean and holds nothing the default branch lacks.")
    lines.append("  clean = the primary checkout; it is not removable.")

    order = {"clean": 0, "dirty": 1, "stale": 2, "active": 3, "missing": 4, "abandoned": 5}
    shown = sorted(
        infos,
        key=lambda i: (0 if i.get("primary") else 1, order.get(i["verdict"], 9), i.get("age") or 0),
    )
    limit = len(shown) if args.full else MAX_WORKTREES
    for info in shown[:limit]:
        name = info.get("branch") or (info.get("head", "")[:8] + " (detached)")
        path = info["path"].replace(str(Path.home()), "~")
        bits = [info["verdict"]]
        if info.get("dirty"):
            bits.append(f"{info['dirty']} changed")
        if info.get("ahead") is not None:
            bits.append(f"+{info['ahead']}/-{info['behind']} vs {db['ref']}")
        if info.get("age") is not None:
            bits.append(f"{info['age']}d old")
        if info.get("locked"):
            bits.append("locked")
        lines.append(f"  {name}")
        lines.append(f"      {path}")
        lines.append(f"      {' · '.join(bits)}")
        if info.get("subject"):
            lines.append(f"      last: {info['subject'][:88]}")
    if len(shown) > limit:
        lines.append(f"  ... and {len(shown) - limit} more; run with --full")

    br = data["branches"]
    lines.append(header(f"Local branches unmerged into {db['ref']} ({len(br['unmerged'])})"))
    n_remote = br["remote_only_unmerged"]
    remote_word = "remote-only branch" + ("" if n_remote == 1 else "es")
    remote_verb = "is" if n_remote == 1 else "are"
    lines.append(
        f"  Local refs only. {n_remote} {remote_word} {remote_verb} also unmerged"
        f" and {remote_verb} not listed."
    )
    if br["unmerged"]:
        limit = len(br["unmerged"]) if args.full else MAX_BRANCHES
        for name in br["unmerged"][:limit]:
            lines.append(f"  {name}")
        if len(br["unmerged"]) > limit:
            lines.append(f"  ... and {len(br['unmerged']) - limit} more; run with --full")
    else:
        lines.append("  none")

    lines.append(header(f"Unpushed local branches ({len(br['unpushed'])})"))
    if br["unpushed"]:
        limit = len(br["unpushed"]) if args.full else MAX_BRANCHES
        for item in br["unpushed"][:limit]:
            lines.append(f"  {item['name']} · {item['why']}")
        if len(br["unpushed"]) > limit:
            lines.append(f"  ... and {len(br['unpushed']) - limit} more; run with --full")
    else:
        lines.append("  none")

    landed = data["landed"]
    lines.append(header(f"On {db['ref']} but not in your HEAD ({landed['total']})"))
    lines.append("  Reported by committer; git does not record who pushed.")
    if landed["commits"]:
        for row in landed["commits"]:
            sha, when, who, subject = (row + ["", "", "", ""])[:4]
            lines.append(f"  {sha}  {when:<16} {who:<18} {subject[:70]}")
        if landed["total"] > len(landed["commits"]):
            lines.append(f"  ... and {landed['total'] - len(landed['commits'])} more; run with --full")
    else:
        lines.append("  nothing; your HEAD has everything on the default branch")
    lines.append("  Reflects the last fetch. This command does not fetch.")

    prs = data["pull_requests"]
    lines.append(header(f"Open pull requests ({len(prs['items'])})" if prs["status"] == "ok"
                        else "Open pull requests"))
    if prs["status"] != "ok":
        lines.append(f"  {prs['status']}: {prs['reason']}")
    elif not prs["items"]:
        lines.append("  none")
    else:
        for pr in prs["items"]:
            tag = " [draft]" if pr["draft"] else ""
            lines.append(f"  #{pr['number']}{tag} {pr['title'][:62]}")
            lines.append(f"      {pr['branch']} · {pr['author']} · checks {pr['ci']}")

    cp = data["checkpoints"]
    lines.append(header("Newest checkpoint"))
    if cp["status"] == "skipped":
        lines.append("  skipped: no --checkpoints directory was given")
    elif cp["status"] == "missing":
        lines.append(f"  no such directory: {cp['dir']}")
    elif cp["status"] == "none":
        lines.append(f"  none found under {cp['dir']}")
    else:
        newest = cp["newest"]
        lines.append(f"  {newest['path']}")
        if newest["age_days"] is not None:
            lines.append(f"  {newest['age_days']:.1f} days old")
        if newest["focus"]:
            lines.append(f"  focus: {newest['focus']}")

    tasks = data["tasks"]
    lines.append(header(f"Open tasks ({len(tasks['lines'])})" if tasks["status"] == "ok"
                        else "Open tasks"))
    if tasks["status"] != "ok":
        lines.append(f"  {tasks['status']}: {tasks['reason']}")
    elif not tasks["lines"]:
        lines.append("  the provider returned nothing")
    else:
        for line in tasks["lines"]:
            lines.append(f"  {line}")
        if tasks["total"] > len(tasks["lines"]):
            lines.append(
                f"  ... and {tasks['total'] - len(tasks['lines'])} more; run with --full"
            )

    return "\n".join(lines)


# --------------------------------------------------------------------------- CLI


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="agent-continuity",
        description="Reconstruct the working state of a repository. Read-only.",
    )
    ap.add_argument("--repo", default=".", help="repository path (default: cwd)")
    ap.add_argument("--full", action="store_true", help="do not truncate long lists")
    ap.add_argument("--no-net", action="store_true", help="skip the GitHub calls")
    ap.add_argument("--no-tasks", action="store_true", help="skip the task provider")
    ap.add_argument("--checkpoints", help="directory to search for checkpoints/*.md")
    ap.add_argument("--tasks-cmd", help="command whose stdout lines are open tasks")
    ap.add_argument("--stale-days", type=int, default=STALE_DAYS,
                    help=f"days without a commit before a clean worktree is stale (default {STALE_DAYS})")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2

    root = repo_root(args.repo)
    if not root:
        print(
            f"agent-continuity: {args.repo} is not inside a git repository, or git is not installed",
            file=sys.stderr,
        )
        return 1

    started = time.time()
    data = collect(root, args)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(render_text(data, args))
        print(f"\n({time.time() - started:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
