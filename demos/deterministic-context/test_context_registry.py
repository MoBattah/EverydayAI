#!/usr/bin/env python3
"""Tests for context_registry.py.

Run: python3 demos/deterministic-context/test_context_registry.py

Every test works on a copy of the checked-in example under the system temp directory.
The checked-in example is never modified.
"""

import contextlib
import hashlib
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import context_registry as cr  # noqa: E402

PASSED = 0
FAILED = 0

HERE = Path(__file__).parent
EXAMPLE = HERE / "example"


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


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cr.main(argv)
    return rc, out.getvalue(), err.getvalue()


def copy_example(td):
    root = Path(tempfile.mkdtemp(dir=td)) / "registry"
    shutil.copytree(EXAMPLE, root)
    return root


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def edit(path, change):
    data = load(path)
    change(data)
    save(path, data)


def snapshot(root):
    digest = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            digest[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def check_registry(root, *extra):
    return run(["--root", str(root), "check", *extra])


def render_registry(root):
    return run(["--root", str(root), "render"])


def blank_regions(root):
    """Empty every generated body, leaving the marker pairs and the hand prose."""
    for path in sorted(Path(root).rglob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        out, inside = [], False
        for line in lines:
            if cr.MARKER_RE.match(line):
                out.append(line)
                inside = cr.MARKER_RE.match(line).group(1) == "BEGIN"
                continue
            if not inside:
                out.append(line)
        path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main():
    print("the checked-in example")
    rc, out, _ = check_registry(EXAMPLE)
    check("the example passes check", rc, 0)
    check_true("every view is counted", "check: 6 views match their records" in out)

    index = (EXAMPLE / "INDEX.md").read_text(encoding="utf-8")
    check_true("the index is sorted by workspace name", index.index("| Alpha |") < index.index("| Beta |"))
    check_true("the dependency is rendered", "| Beta | Paused |" in index and "| Alpha |" in index)
    check_true("hand prose outside the markers survives", "## Reading this index" in index)

    alpha = (EXAMPLE / "registry" / "workspaces" / "alpha" / "README.md").read_text(encoding="utf-8")
    check_true("the workspace status line is rendered", "**Status:** Active since 2026-01-15" in alpha)
    check_true("workspace notes stay outside the region", "## Notes" in alpha)

    rc, out, _ = run(["--root", str(EXAMPLE), "context", "alpha-agent"])
    check("context for an agent exits 0", rc, 0)
    check_true("the agent's own workspace is present", "## Alpha (Active since 2026-01-15)" in out)
    check_true("another workspace is absent", "Beta" not in out)
    check_true("the status vocabulary is explained", "**Active**: Work is moving" in out)

    rc, out, _ = run(["--root", str(EXAMPLE), "context", "portfolio-agent"])
    check("the wildcard agent exits 0", rc, 0)
    check_true("the wildcard agent sees every workspace", "## Alpha" in out and "## Beta" in out)
    check_true("both statuses are explained", "**Active**" in out and "**Paused**" in out)

    rc, out, _ = run(["--root", str(EXAMPLE), "context", "beta-agent", "--json"])
    check("context --json exits 0", rc, 0)
    data = json.loads(out)
    check("the JSON names the agent", data["agent"], "beta-agent")
    check("the JSON carries one workspace", [w["name"] for w in data["workspaces"]], ["Beta"])
    check("the workspace fields are present", sorted(data["workspaces"][0]),
          ["name", "status", "status_note", "status_since", "summary"])
    check("the JSON vocabulary is limited to used statuses",
          [s["name"] for s in data["vocabulary"]], ["Paused"])

    rc, _, err = run(["--root", str(EXAMPLE), "context", "nobody"])
    check("an unknown agent exits 3", rc, 3)
    check_true("and the known agents are listed", "known agents: alpha-agent, beta-agent, portfolio-agent" in err)

    with tempfile.TemporaryDirectory() as td:
        print("\nrendering and drift")
        root = copy_example(td)
        rc, out, _ = render_registry(root)
        check("a current registry writes nothing", rc, 0)
        check_true("render reports every view current", "render: 0 written, 6 already current" in out)

        before = snapshot(root)
        blank_regions(root)
        check_true("blanking the bodies changes the files", snapshot(root) != before)
        rc, out, _ = render_registry(root)
        check("render rebuilds every body", rc, 0)
        check_true("all six are written", "render: 6 written, 0 already current" in out)
        check("the rebuilt bytes match the first render", snapshot(root), before)

        edit(root / "registry" / "workspaces" / "alpha" / "project.json",
             lambda d: d.update(status="Paused", status_since="2026-03-01",
                                status_note="Paused while the schema is rewritten"))
        rc, out, _ = check_registry(root)
        check("a changed record makes check exit 1", rc, 1)
        stale = [line[len("stale: "):] for line in out.splitlines() if line.startswith("stale: ")]
        check("every dependent view is named", stale, [
            "INDEX.md",
            "context/alpha-agent.md",
            "context/portfolio-agent.md",
            "registry/workspaces/alpha/README.md",
        ])
        check_true("the stale summary counts them", "check: 4 of 6 views are stale" in out)

        rc, out, _ = render_registry(root)
        check("render fixes the drift", rc, 0)
        check_true("four views are written", "render: 4 written, 2 already current" in out)
        rc, out, _ = check_registry(root)
        check("check passes after render", rc, 0)

        alpha = (root / "registry" / "workspaces" / "alpha" / "README.md").read_text(encoding="utf-8")
        check_true("the new status is rendered", "**Status:** Paused since 2026-03-01" in alpha)
        check_true("hand prose survives the rewrite", "Hand-written prose belongs outside" in alpha)

        rc, out, _ = render_registry(root)
        check_true("a second render is a no-op", "render: 0 written, 6 already current" in out)

        print("\ndeterministic ordering")
        shutil.copytree(root / "registry" / "workspaces" / "beta",
                        root / "registry" / "workspaces" / "aardvark")
        edit(root / "registry" / "workspaces" / "aardvark" / "project.json",
             lambda d: d.update(name="Aardvark", depends_on=[]))
        (root / "registry" / "workspaces" / "aardvark" / "README.md").write_text(
            "# Aardvark\n\n<!-- BEGIN GENERATED:workspace-status -->\n"
            "<!-- END GENERATED:workspace-status -->\n",
            encoding="utf-8",
        )
        rc, out, _ = render_registry(root)
        check("a new workspace renders", rc, 0)
        index = (root / "INDEX.md").read_text(encoding="utf-8")
        check_true("the new row sorts first", index.index("| Aardvark |") < index.index("| Alpha |"))
        rc, out, _ = check_registry(root)
        check("the registry is current again", rc, 0)

        print("\nmarker failures")
        root = copy_example(td)
        path = root / "context" / "alpha-agent.md"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(l for l in lines if "GENERATED" not in l) + "\n",
                        encoding="utf-8")
        rc, out, _ = check_registry(root)
        check("a missing pair is invalid", rc, 2)
        check_true("the missing pair is named",
                   "expected one BEGIN/END GENERATED:agent-context pair, found 0" in out)

        root = copy_example(td)
        path = root / "context" / "alpha-agent.md"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n<!-- BEGIN GENERATED:agent-context -->\n"
            + "<!-- END GENERATED:agent-context -->\n",
            encoding="utf-8",
        )
        rc, out, _ = check_registry(root)
        check("a duplicated pair is invalid", rc, 2)
        check_true("the duplicate count is reported", "pair, found 2" in out)

        root = copy_example(td)
        path = root / "context" / "alpha-agent.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "END GENERATED:agent-context", "END GENERATED:workspace-status"
            ),
            encoding="utf-8",
        )
        rc, out, _ = check_registry(root)
        check("mismatched marker names are invalid", rc, 2)
        check_true("the mismatch names both markers",
                   "END GENERATED:workspace-status closes BEGIN GENERATED:agent-context" in out)

        root = copy_example(td)
        path = root / "context" / "beta-agent.md"
        path.write_text(
            "<!-- END GENERATED:agent-context -->\n" + path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        rc, out, _ = check_registry(root)
        check("a stray END is invalid", rc, 2)
        check_true("the stray marker is reported", "END GENERATED:agent-context has no matching BEGIN" in out)

        root = copy_example(td)
        path = root / "context" / "beta-agent.md"
        path.write_text(
            "\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                      if "END GENERATED" not in l) + "\n",
            encoding="utf-8",
        )
        rc, out, _ = check_registry(root)
        check("an unclosed BEGIN is invalid", rc, 2)
        check_true("the unclosed marker is reported", "is never closed" in out)

        root = copy_example(td)
        (root / "context" / "beta-agent.md").unlink()
        rc, out, _ = check_registry(root)
        check("a missing view file is invalid", rc, 2)
        check_true("the missing file is named", "context/beta-agent.md: missing" in out)

        root = copy_example(td)
        path = root / "context" / "alpha-agent.md"
        path.write_text("\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                                  if "BEGIN GENERATED" not in l) + "\n", encoding="utf-8")
        before = snapshot(root)
        rc, out, _ = render_registry(root)
        check("render refuses a missing marker", rc, 2)
        check("render writes nothing when a marker is invalid", snapshot(root), before)

        root = copy_example(td)
        edit(root / "registry" / "workspaces" / "alpha" / "project.json",
             lambda d: d.update(status="Paused"))
        path = root / "context" / "beta-agent.md"
        path.write_text("\n".join(l for l in path.read_text(encoding="utf-8").splitlines()
                                  if "END GENERATED" not in l) + "\n", encoding="utf-8")
        before = snapshot(root)
        rc, out, _ = render_registry(root)
        check("a late marker failure aborts the whole render", rc, 2)
        check("no earlier view was written before the failure", snapshot(root), before)

        print("\ninvalid records")
        cases = [
            ("an unknown status", "registry/workspaces/alpha/project.json",
             lambda d: d.update(status="Banana"), "not in the vocabulary"),
            ("an unknown key", "registry/workspaces/alpha/project.json",
             lambda d: d.update(owner="team-alpha"), "unknown key 'owner'"),
            ("a name that does not match the directory", "registry/workspaces/alpha/project.json",
             lambda d: d.update(name="Gamma"), "does not match the directory"),
            ("a pipe in the summary", "registry/workspaces/alpha/project.json",
             lambda d: d.update(summary="a | b"), "must not contain '|'"),
            ("an overlong summary", "registry/workspaces/alpha/project.json",
             lambda d: d.update(summary="x" * 200), "the limit is 160"),
            ("a bad date", "registry/workspaces/alpha/project.json",
             lambda d: d.update(status_since="not-a-date"), "is not an ISO date"),
            ("a self dependency", "registry/workspaces/alpha/project.json",
             lambda d: d.update(depends_on=["Alpha"]), "depends_on names itself"),
            ("an unknown dependency", "registry/workspaces/alpha/project.json",
             lambda d: d.update(depends_on=["Gamma"]), "unknown workspace 'Gamma'"),
            ("a dependency cycle", "registry/workspaces/alpha/project.json",
             lambda d: d.update(depends_on=["Beta"]), "depends_on cycle: Alpha -> Beta -> Alpha"),
            ("a duplicate agent id", "registry/agents.json",
             lambda d: d["agents"].append(dict(d["agents"][0])), "is defined twice"),
            ("an agent naming an unknown workspace", "registry/agents.json",
             lambda d: d["agents"][0].update(workspaces=["Gamma"]), "names unknown workspace 'Gamma'"),
            ("a wildcard with another name", "registry/agents.json",
             lambda d: d["agents"][0].update(workspaces=["*", "Alpha"]), "'*' must stand alone"),
            ("a duplicate status", "registry/vocabulary.json",
             lambda d: d["statuses"].append(dict(d["statuses"][0])), "is defined twice"),
            ("an unsupported version", "registry/vocabulary.json",
             lambda d: d.update(version=2), "version must be 1"),
        ]
        for label, rel, change, expected in cases:
            root = copy_example(td)
            edit(root / rel, change)
            rc, out, _ = check_registry(root)
            check(f"{label} is rejected", rc, 2)
            check_true(f"{label} names the problem", expected in out)

        root = copy_example(td)
        (root / "registry" / "vocabulary.json").write_text("{not json", encoding="utf-8")
        rc, out, _ = check_registry(root)
        check("unparseable JSON is rejected", rc, 2)
        check_true("the parse error is named", "not valid JSON" in out)

        root = copy_example(td)
        edit(root / "registry" / "workspaces" / "alpha" / "project.json",
             lambda d: d.update(status="Banana"))
        before = snapshot(root)
        rc, out, _ = render_registry(root)
        check("render refuses invalid data", rc, 2)
        check("render writes nothing when data is invalid", snapshot(root), before)

        print("\nread-only commands")
        root = copy_example(td)
        before = snapshot(root)
        rc, _, _ = check_registry(root)
        check("check exits 0 before the snapshot is read", rc, 0)
        rc, _, _ = run(["--root", str(root), "context", "portfolio-agent"])
        check("context exits 0", rc, 0)
        check("check and context change no file", snapshot(root), before)

        print("\nusage")
        rc, _, _ = run([])
        check("no subcommand exits 3", rc, 3)
        rc, _, _ = run(["--root", str(Path(td) / "nowhere"), "check"])
        check("a missing root exits 3", rc, 3)

    print(f"\n{PASSED} passed, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
