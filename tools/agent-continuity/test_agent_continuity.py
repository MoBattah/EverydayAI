#!/usr/bin/env python3
"""Tests for agent_continuity.py.

Run: python3 tools/agent-continuity/test_agent_continuity.py

Every test builds a throwaway Git repository under the system temp directory. No
network, account or GitHub CLI is required: gh is stubbed on PATH.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import agent_continuity as ac  # noqa: E402

PASSED = 0
FAILED = 0

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Demo",
    "GIT_AUTHOR_EMAIL": "demo@example.com",
    "GIT_COMMITTER_NAME": "Demo",
    "GIT_COMMITTER_EMAIL": "demo@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_TERMINAL_PROMPT": "0",
}


def check(name, got, want):
    global PASSED, FAILED
    if got == want:
        PASSED += 1
        print(f"  pass  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}\n          got:  {got!r}\n          want: {want.__class__.__name__} {want!r}")


def check_true(name, cond, detail=""):
    check(f"{name} {detail}".rstrip(), bool(cond), True)


def sh(cwd, *args, env=None, quiet=True):
    e = {**os.environ, **GIT_ENV, **(env or {})}
    p = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=e,
    )
    if p.returncode != 0 and not quiet:
        raise RuntimeError(f"git {' '.join(args)} failed: {p.stderr}")
    return p


def commit(repo, message, when=None):
    env = {}
    if when:
        env = {"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    (Path(repo) / "file.txt").write_text(message + "\n", encoding="utf-8")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", message, env=env)


def make_remote(base):
    """A bare origin plus a clone with one commit on main and origin/HEAD set."""
    origin = Path(base) / "origin.git"
    work = Path(base) / "work"
    sh(base, "init", "--bare", "-q", str(origin))
    sh(base, "clone", "-q", str(origin), str(work))
    commit(work, "initial commit")
    sh(work, "branch", "-M", "main")
    sh(work, "push", "-q", "-u", "origin", "main")
    sh(origin, "symbolic-ref", "HEAD", "refs/heads/main")
    sh(work, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    return origin, work


def run_tool(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = ac.main(argv)
    return rc, buf.getvalue()


def run_json(repo, *extra):
    rc, out = run_tool(["--repo", str(repo), "--json", *extra])
    return rc, json.loads(out)


def context(repo, *extra):
    rc, out = run_tool(["--repo", str(repo), *extra])
    return rc, out


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def executable(path, body):
    write(path, body)
    Path(path).chmod(0o755)
    return Path(path)


def main():
    print("github_slug")
    cases = [
        ("https://github.com/acme/widget.git", "acme/widget"),
        ("https://github.com/acme/widget", "acme/widget"),
        ("git@github.com:acme/widget.git", "acme/widget"),
        ("ssh://git@github.com/acme/widget.git", "acme/widget"),
        ("git@github-work:acme/widget.git", "acme/widget"),
        ("https://gitlab.com/acme/widget.git", None),
        ("git@gitlab.com:acme/widget.git", None),
        ("https://example.com/acme/widget", None),
        ("", None),
    ]
    for url, want in cases:
        check(f"{url or 'empty'} -> {want}", ac.github_slug(url), want)

    with tempfile.TemporaryDirectory() as td:
        print("\nclean repository")
        origin, work = make_remote(td)
        rc, data = run_json(work, "--no-net")
        check("exits 0", rc, 0)
        check("default branch comes from origin/HEAD", data["default_branch"]["source"], "origin/HEAD")
        check("default branch is main", data["default_branch"]["name"], "main")
        check("HEAD is clean", data["head"]["dirty"], 0)
        check("one worktree", len(data["worktrees"]), 1)
        check("the primary checkout is labelled clean, never abandoned",
              data["worktrees"][0]["verdict"], "clean")
        check("no unmerged branches", data["branches"]["unmerged"], [])
        check("no unpushed branches", data["branches"]["unpushed"], [])
        check("nothing landed", data["landed"]["total"], 0)
        check("network is skipped on request", data["pull_requests"]["status"], "skipped")
        check("checkpoints are skipped by default", data["checkpoints"]["status"], "skipped")
        check("tasks are skipped without a provider", data["tasks"]["status"], "skipped")
        check("the remote is recorded", data["remote"], str(origin))

        rc, text = context(work, "--no-net")
        check_true("the text report names the branch", "default branch main" in text)
        check_true("the text report says the tree is clean", "tree clean" in text)
        check_true("the text report says it did not fetch", "This command does not fetch." in text)

        print("\ndirty state and branches")
        sh(work, "checkout", "-q", "-b", "feature/report")
        commit(work, "feature work")
        sh(work, "checkout", "-q", "main")
        sh(work, "branch", "merged-only", "main")
        sh(work, "checkout", "-q", "-b", "remote-only")
        commit(work, "remote only work")
        sh(work, "push", "-q", "origin", "remote-only")
        sh(work, "checkout", "-q", "main")
        sh(work, "branch", "-D", "-q", "remote-only")
        sh(work, "fetch", "-q", "origin")
        write(Path(work) / "README.md", "changed\n")
        write(Path(work) / "untracked.txt", "new\n")

        rc, data = run_json(work, "--no-net")
        check("dirty counts modified and untracked files", data["head"]["dirty"], 2)
        check("the feature branch is unmerged", "feature/report" in data["branches"]["unmerged"], True)
        check("merged-only is filtered from unpushed", [b["name"] for b in data["branches"]["unpushed"]],
              ["feature/report"])
        check("the unpushed reason is stated", data["branches"]["unpushed"][0]["why"],
              "no upstream, holds unmerged commits")
        check_true("a remote-only unmerged branch is counted",
                   data["branches"]["remote_only_unmerged"] >= 1)
        rc, text = context(work, "--no-net")
        check_true("a single remote-only branch is described in the singular",
                   "1 remote-only branch is also unmerged" in text)

        sh(work, "checkout", "-q", "-b", "remote-only-2")
        commit(work, "second remote only work")
        sh(work, "push", "-q", "origin", "remote-only-2")
        sh(work, "checkout", "-q", "main")
        sh(work, "branch", "-D", "-q", "remote-only-2")
        sh(work, "fetch", "-q", "origin")
        rc, text = context(work, "--no-net")
        check_true("several remote-only branches are described in the plural",
                   "2 remote-only branches are also unmerged" in text)

        print("\nunpushed commits against a tracked upstream")
        sh(work, "checkout", "-q", "-b", "feature/tracked")
        commit(work, "tracked one")
        sh(work, "push", "-q", "-u", "origin", "feature/tracked")
        commit(work, "tracked two")
        rc, data = run_json(work, "--no-net")
        tracked = [b for b in data["branches"]["unpushed"] if b["name"] == "feature/tracked"]
        check("a tracked branch ahead of its upstream is reported", len(tracked), 1)
        check_true("the ahead count is in the reason", "ahead" in tracked[0]["why"])
        sh(work, "checkout", "-q", "main")

        print("\nlanded commits and the no-fetch guarantee")
        other = Path(td) / "other"
        sh(td, "clone", "-q", str(origin), str(other))
        sh(other, "config", "user.name", "Other")
        sh(other, "config", "user.email", "other@example.com")
        commit(other, "landed upstream")
        sh(other, "push", "-q", "origin", "main")

        rc, data = run_json(work, "--no-net")
        check("a commit that was not fetched is not reported", data["landed"]["total"], 0)

        sh(work, "fetch", "-q", "origin")
        rc, data = run_json(work, "--no-net")
        check("after a manual fetch it is reported", data["landed"]["total"], 1)
        check_true("the landed subject is reported", "landed upstream" in data["landed"]["commits"][0][3])

        rc, text = context(work, "--no-net")
        check_true("the report says which ref it compares against", "origin/main" in text)

        print("\nworktree verdicts")
        base = Path(td) / "trees"
        base.mkdir()
        sh(work, "worktree", "add", "-q", str(base / "abandoned"), "-b", "wt-abandoned", "main")
        sh(work, "worktree", "add", "-q", str(base / "dirty"), "-b", "wt-dirty", "main")
        write(base / "dirty" / "draft.txt", "draft\n")
        sh(work, "worktree", "add", "-q", str(base / "stale"), "-b", "wt-stale", "main")

        old = (date.today() - timedelta(days=30)).isoformat() + "T12:00:00"
        env = {"GIT_AUTHOR_DATE": old, "GIT_COMMITTER_DATE": old}
        write(base / "stale" / "file.txt", "old work\n")
        sh(base / "stale", "add", "-A")
        sh(base / "stale", "commit", "-q", "-m", "old work", env=env)

        sh(work, "worktree", "add", "-q", "--detach", str(base / "detached"), "main")

        gone = base / "gone"
        sh(work, "worktree", "add", "-q", str(gone), "-b", "wt-gone", "main")
        shutil.rmtree(gone)

        rc, data = run_json(work, "--no-net")
        by_branch = {w.get("branch"): w for w in data["worktrees"] if w.get("branch")}
        check("a clean worktree with no extra commits is abandoned",
              by_branch["wt-abandoned"]["verdict"], "abandoned")
        check("a dirty worktree is dirty", by_branch["wt-dirty"]["verdict"], "dirty")
        check("a clean worktree with month-old unmerged work is stale",
              by_branch["wt-stale"]["verdict"], "stale")
        check("a missing worktree path is reported", by_branch["wt-gone"]["verdict"], "missing")
        check_true("the detached worktree is marked", any(w.get("detached") for w in data["worktrees"]))

        rc, text = context(work, "--no-net")
        check_true("the text report explains the verdicts", "abandoned = clean and holds nothing" in text)
        check_true("the text report separates the primary checkout", "clean = the primary checkout" in text)
        check_true("the default stale threshold is stated", "no commit in 14 days" in text)
        rc, data = run_json(work, "--no-net", "--stale-days", "45")
        by_branch = {w.get("branch"): w for w in data["worktrees"] if w.get("branch")}
        check("raising the threshold makes the worktree active",
              by_branch["wt-stale"]["verdict"], "active")

        print("\npull requests through a stubbed gh")
        sh(work, "remote", "set-url", "origin", "https://github.com/acme/widget.git")
        bin_dir = Path(td) / "bin"
        bin_dir.mkdir()
        executable(bin_dir / "gh", """#!/bin/sh
cat <<'JSON'
[
  {"number": 7, "title": "Add the report", "headRefName": "feature/report",
   "author": {"login": "demo"}, "isDraft": false,
   "statusCheckRollup": [{"conclusion": "SUCCESS"}]},
  {"number": 8, "title": "Draft scaffolding", "headRefName": "feature/scaffold",
   "author": {"login": "other"}, "isDraft": true,
   "statusCheckRollup": [{"conclusion": "FAILURE"}]},
  {"number": 9, "title": "Waiting on CI", "headRefName": "feature/wait",
   "author": {"login": "demo"}, "isDraft": false,
   "statusCheckRollup": [{"status": "IN_PROGRESS"}]},
  {"number": 10, "title": "No checks yet", "headRefName": "feature/none",
   "author": {"login": "demo"}, "isDraft": false, "statusCheckRollup": []},
  {"number": 11, "title": "An unknown state", "headRefName": "feature/odd",
   "author": {"login": "demo"}, "isDraft": false,
   "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"conclusion": "STALE"}]}
]
JSON
""")
        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
            rc, data = run_json(work)
            check("pull requests are read", data["pull_requests"]["status"], "ok")
            items = {pr["number"]: pr for pr in data["pull_requests"]["items"]}
            check("passing checks are summarised", items[7]["ci"], "passing")
            check("failing checks are summarised", items[8]["ci"], "failing")
            check("running checks are summarised", items[9]["ci"], "running")
            check("an empty rollup says no checks", items[10]["ci"], "no checks")
            check("an unrecognised check state is mixed", items[11]["ci"], "mixed")
            check("a draft is marked", items[8]["draft"], True)

            executable(bin_dir / "gh", "#!/bin/sh\necho 'not logged in' >&2\nexit 1\n")
            rc, data = run_json(work)
            check("a failing gh is unavailable", data["pull_requests"]["status"], "unavailable")
            check_true("and its own message is passed through",
                       "not logged in" in data["pull_requests"]["reason"])
        finally:
            os.environ["PATH"] = old_path

        print("\ncheckpoints")
        cps = Path(work) / "checkpoints"
        write(cps / "2026-01-05-0900.md", "# old\n\n**Session focus:** old focus\n")
        write(cps / "2026-02-10-1400.md", "# new\n\n**Session focus:** the newer focus\n")
        write(Path(work) / ".hidden" / "checkpoints" / "2026-03-01-0000.md", "hidden\n")
        write(Path(work) / "node_modules" / "checkpoints" / "2026-03-02-0000.md", "ignored\n")
        rc, data = run_json(work, "--no-net", "--checkpoints", ".")
        check("the newest checkpoint is chosen by file name", data["checkpoints"]["status"], "ok")
        newest = data["checkpoints"]["newest"]
        check_true("the newest file wins", newest["path"].endswith("2026-02-10-1400.md"))
        check("the focus line is parsed", newest["focus"], "the newer focus")
        expected_age = (date.today() - date(2026, 2, 10)).days
        check("age comes from the date in the name", newest["age_days"], expected_age)
        check("hidden directories are skipped", "2026-03-01" in json.dumps(data["checkpoints"]), False)
        check("node_modules is skipped", "2026-03-02" in json.dumps(data["checkpoints"]), False)

        rc, data = run_json(work, "--no-net", "--checkpoints", "no-such-dir")
        check("a missing checkpoint directory is named", data["checkpoints"]["status"], "missing")

        empty = Path(td) / "empty-checkpoints"
        empty.mkdir()
        rc, data = run_json(work, "--no-net", "--checkpoints", str(empty))
        check("an empty checkpoint directory says none", data["checkpoints"]["status"], "none")

        print("\ntask providers")
        provider = executable(Path(td) / "tasks.sh",
                              "#!/bin/sh\necho '- [ ] Send the report'\necho '- [ ] Book the room'\n")
        bad_provider = executable(Path(td) / "bad-tasks.sh",
                                  "#!/bin/sh\necho 'registry unavailable' >&2\nexit 1\n")
        rc, data = run_json(work, "--no-net", "--tasks-cmd", str(provider))
        check("a provider's lines are collected", data["tasks"]["status"], "ok")
        check("both tasks are present", data["tasks"]["lines"],
              ["- [ ] Send the report", "- [ ] Book the room"])
        check("the total is retained", data["tasks"]["total"], 2)
        check("the task total does not overwrite the landed total",
              data["landed"]["total"], 1)

        rc, data = run_json(work, "--no-net", "--tasks-cmd", str(bad_provider))
        check("a failing provider is unavailable", data["tasks"]["status"], "unavailable")
        check_true("and its message is passed through", "registry unavailable" in data["tasks"]["reason"])

        rc, data = run_json(work, "--no-net", "--tasks-cmd", str(provider), "--no-tasks")
        check("--no-tasks wins over a configured provider", data["tasks"]["status"], "skipped")

        print("\nread-only guarantee")
        def snapshot(repo):
            out = {}
            for p in sorted(Path(repo).rglob("*")):
                if p.is_file() and not p.is_symlink():
                    st = p.stat()
                    out[str(p.relative_to(repo))] = (st.st_size, st.st_mtime_ns)
            return out

        status_before = sh(work, "status", "--porcelain",
                           env={"GIT_OPTIONAL_LOCKS": "0"}).stdout
        before = snapshot(work)
        rc, _ = run_tool(["--repo", str(work), "--no-net", "--checkpoints", ".",
                          "--tasks-cmd", str(provider)])
        after = snapshot(work)
        status_after = sh(work, "status", "--porcelain",
                          env={"GIT_OPTIONAL_LOCKS": "0"}).stdout
        check("the command exits 0", rc, 0)
        check("no file under the repository changes", after, before)
        check("the working tree status is unchanged", status_after, status_before)

        print("\ndefault branch resolution without origin/HEAD")
        local = Path(td) / "local-only"
        sh(td, "init", "-q", str(local))
        commit(local, "local")
        rc, data = run_json(local, "--no-net")
        check("a repository with no remote falls back to its current branch",
              data["default_branch"]["source"], "fell back to the current branch")

        master_origin = Path(td) / "master-origin.git"
        master_work = Path(td) / "master-work"
        sh(td, "init", "--bare", "-q", str(master_origin))
        sh(td, "clone", "-q", str(master_origin), str(master_work))
        commit(master_work, "master commit")
        sh(master_work, "branch", "-M", "master")
        sh(master_work, "push", "-q", "-u", "origin", "master")
        rc, data = run_json(master_work, "--no-net")
        check("without origin/HEAD a conventional remote branch is guessed",
              data["default_branch"]["source"], "guessed from remote refs")
        check("and the guessed branch is master", data["default_branch"]["name"], "master")

        print("\ntruncation and --full")
        for i in range(14):
            sh(work, "checkout", "-q", "-b", f"queue/{i}", "main")
            sh(work, "commit", "-q", "--allow-empty", "-m", f"queue {i}")
        sh(work, "checkout", "-q", "main")
        rc, text = context(work, "--no-net")
        check_true("long branch lists are truncated", "more; run with --full" in text)
        rc, text = context(work, "--no-net", "--full")
        check_true("--full prints every branch", "queue/13" in text)

        print("\nnot a repository")
        plain = Path(td) / "plain"
        plain.mkdir()
        rc, _ = run_tool(["--repo", str(plain)])
        check("a non-repository exits 1", rc, 1)
        rc, _ = run_tool(["--repo", str(Path(td) / "nowhere")])
        check("a missing path exits 1", rc, 1)
        rc, _ = run_tool(["--no-such-flag"])
        check("a usage error exits 2", rc, 2)

    print(f"\n{PASSED} passed, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
