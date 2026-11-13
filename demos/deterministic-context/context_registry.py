#!/usr/bin/env python3
"""context_registry: operational facts as data, every view generated from them.

One fact has one home. Each workspace is a JSON record; the status vocabulary and the
agent definitions are JSON too. Every Markdown view, the index, each workspace README
status block and each agent's assembled context, is generated from those records inside
a marked region. `check` fails when a record is invalid or a view has drifted.

The command never guesses where generated text belongs. A view becomes a target only
when its file carries a matching BEGIN/END GENERATED pair, and a missing or ambiguous
pair is an error. Prose outside the markers is never touched.

Usage:
  context_registry.py [--root DIR] check
  context_registry.py [--root DIR] render
  context_registry.py [--root DIR] context AGENT [--json]

Exit status:
  0  every view matches its records
  1  a view is stale; run render
  2  a record or a marker is invalid
  3  a usage error, a missing root, or an unknown agent
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

MARKER_RE = re.compile(r"^\s*<!--\s*(BEGIN|END) GENERATED:([a-z0-9][a-z0-9-]*)\s*-->\s*$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

MAX_TEXT = 160

PROJECT_KEYS = {
    "version",
    "name",
    "status",
    "status_since",
    "status_note",
    "summary",
    "depends_on",
}

AGENT_KEYS = {"id", "purpose", "workspaces"}


class Invalid(Exception):
    """One or more problems with the records or the markers."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("invalid registry")


# --------------------------------------------------------------------------- reading


def read_json(path, errors, rel):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        errors.append(f"{rel}: missing")
        return None
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"{rel}: cannot be read ({exc})")
        return None
    except json.JSONDecodeError as exc:
        errors.append(f"{rel}: not valid JSON ({exc.msg} at line {exc.lineno})")
        return None
    if not isinstance(data, dict):
        errors.append(f"{rel}: the top level must be an object")
        return None
    return data


def check_keys(data, required, rel, errors):
    missing = sorted(required - set(data))
    extra = sorted(set(data) - required)
    for key in missing:
        errors.append(f"{rel}: missing key '{key}'")
    for key in extra:
        errors.append(f"{rel}: unknown key '{key}'")


def text_problem(value, label, limit=MAX_TEXT):
    if not isinstance(value, str) or not value.strip():
        return f"{label} must be a non-empty string"
    if "\n" in value or "\r" in value:
        return f"{label} must fit on one line"
    if "|" in value:
        return f"{label} must not contain '|'"
    if len(value) > limit:
        return f"{label} is {len(value)} characters; the limit is {limit}"
    return None


def load_vocabulary(root, errors):
    rel = "registry/vocabulary.json"
    data = read_json(root / rel, errors, rel)
    if data is None:
        return []
    check_keys(data, {"version", "statuses"}, rel, errors)
    if data.get("version") != 1:
        errors.append(f"{rel}: version must be 1")
    statuses = data.get("statuses")
    if not isinstance(statuses, list) or not statuses:
        errors.append(f"{rel}: statuses must be a non-empty list")
        return []

    seen, vocab = set(), []
    for index, item in enumerate(statuses):
        label = f"{rel}: statuses[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: must be an object")
            continue
        check_keys(item, {"name", "definition"}, label, errors)
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label}.name: must be a non-empty string")
            continue
        if name in seen:
            errors.append(f"{label}.name: '{name}' is defined twice")
            continue
        seen.add(name)
        problem = text_problem(item.get("definition"), f"{label}.definition")
        if problem:
            errors.append(problem)
        vocab.append({"name": name, "definition": item.get("definition")})
    return vocab


def load_workspaces(root, errors):
    base = root / "registry" / "workspaces"
    if not base.is_dir():
        errors.append("registry/workspaces: missing")
        return {}
    dirs = sorted(p for p in base.iterdir() if p.is_dir())
    if not dirs:
        errors.append("registry/workspaces: no workspace directories")
        return {}

    workspaces = {}
    for folder in dirs:
        rel = f"registry/workspaces/{folder.name}/project.json"
        data = read_json(folder / "project.json", errors, rel)
        if data is None:
            continue
        check_keys(data, PROJECT_KEYS, rel, errors)
        if data.get("version") != 1:
            errors.append(f"{rel}: version must be 1")
        name = data.get("name")
        problem = text_problem(name, f"{rel}: name", limit=40)
        if problem:
            errors.append(problem)
            continue
        if name.casefold() != folder.name.casefold():
            errors.append(
                f"{rel}: name {name!r} does not match the directory '{folder.name}'"
            )
        if name in workspaces:
            errors.append(f"{rel}: name {name!r} is used by another workspace")
            continue
        if not isinstance(data.get("status"), str):
            errors.append(f"{rel}: status must be a string")
        since = data.get("status_since")
        if since is not None:
            if not isinstance(since, str):
                errors.append(f"{rel}: status_since must be a date or null")
            else:
                try:
                    date.fromisoformat(since)
                except ValueError:
                    errors.append(f"{rel}: status_since {since!r} is not an ISO date")
        for field in ("status_note", "summary"):
            problem = text_problem(data.get(field), f"{rel}: {field}")
            if problem:
                errors.append(problem)
        depends = data.get("depends_on")
        if not isinstance(depends, list) or not all(isinstance(d, str) for d in depends):
            errors.append(f"{rel}: depends_on must be a list of workspace names")
            depends = []
        if len(set(depends)) != len(depends):
            errors.append(f"{rel}: depends_on contains a duplicate")
        workspaces[name] = {
            "name": name,
            "slug": folder.name,
            "status": data.get("status"),
            "status_since": since,
            "status_note": data.get("status_note"),
            "summary": data.get("summary"),
            "depends_on": depends,
        }
    return workspaces


def load_agents(root, errors):
    rel = "registry/agents.json"
    data = read_json(root / rel, errors, rel)
    if data is None:
        return []
    check_keys(data, {"version", "agents"}, rel, errors)
    if data.get("version") != 1:
        errors.append(f"{rel}: version must be 1")
    agents = data.get("agents")
    if not isinstance(agents, list) or not agents:
        errors.append(f"{rel}: agents must be a non-empty list")
        return []

    seen, out = set(), []
    for index, item in enumerate(agents):
        label = f"{rel}: agents[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: must be an object")
            continue
        check_keys(item, AGENT_KEYS, label, errors)
        agent_id = item.get("id")
        if not isinstance(agent_id, str) or not ID_RE.match(agent_id):
            errors.append(f"{label}.id: must be lowercase letters, digits and hyphens")
            continue
        if agent_id in seen:
            errors.append(f"{label}.id: '{agent_id}' is defined twice")
            continue
        seen.add(agent_id)
        problem = text_problem(item.get("purpose"), f"{label}.purpose")
        if problem:
            errors.append(problem)
        names = item.get("workspaces")
        if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
            errors.append(f"{label}.workspaces: must be a non-empty list of names")
            names = []
        if "*" in names and len(names) != 1:
            errors.append(f"{label}.workspaces: '*' must stand alone")
        out.append(
            {"id": agent_id, "purpose": item.get("purpose"), "workspaces": names}
        )
    return sorted(out, key=lambda a: a["id"])


def check_links(vocabulary, workspaces, agents, errors):
    statuses = {s["name"] for s in vocabulary}
    for name, workspace in sorted(workspaces.items()):
        rel = f"registry/workspaces/{workspace['slug']}/project.json"
        if workspace["status"] not in statuses:
            errors.append(
                f"{rel}: status {workspace['status']!r} is not in the vocabulary"
            )
        for dep in workspace["depends_on"]:
            if dep == name:
                errors.append(f"{rel}: depends_on names itself")
            elif dep not in workspaces:
                errors.append(f"{rel}: depends_on names unknown workspace {dep!r}")

    cycle = find_cycle(workspaces)
    if cycle:
        errors.append("registry/workspaces: depends_on cycle: " + " -> ".join(cycle))

    known = set(workspaces)
    for agent in agents:
        rel = f"registry/agents.json: {agent['id']}"
        if "*" in agent["workspaces"]:
            continue
        for name in agent["workspaces"]:
            if name not in known:
                errors.append(f"{rel}: names unknown workspace {name!r}")


def find_cycle(workspaces):
    """Return one dependency cycle as a list of names, or None."""
    state = {}

    def visit(name, stack):
        state[name] = "open"
        stack.append(name)
        for dep in workspaces[name]["depends_on"]:
            if dep not in workspaces:
                continue
            if state.get(dep) == "open":
                return stack[stack.index(dep):] + [dep]
            if state.get(dep) is None:
                found = visit(dep, stack)
                if found:
                    return found
        stack.pop()
        state[name] = "done"
        return None

    for name in sorted(workspaces):
        if state.get(name) is None:
            found = visit(name, [])
            if found:
                return found
    return None


def load_registry(root):
    errors = []
    vocabulary = load_vocabulary(root, errors)
    workspaces = load_workspaces(root, errors)
    agents = load_agents(root, errors)
    check_links(vocabulary, workspaces, agents, errors)
    if errors:
        raise Invalid(errors)
    return {"vocabulary": vocabulary, "workspaces": workspaces, "agents": agents}


# --------------------------------------------------------------------------- views


def since_suffix(workspace):
    return f" since {workspace['status_since']}" if workspace["status_since"] else ""


def workspace_names(agent, workspaces):
    if "*" in agent["workspaces"]:
        return sorted(workspaces)
    return sorted(agent["workspaces"])


def index_body(registry):
    lines = ["| Workspace | Status | Summary | Depends on |", "|---|---|---|---|"]
    for name in sorted(registry["workspaces"]):
        workspace = registry["workspaces"][name]
        depends = ", ".join(workspace["depends_on"]) or "none"
        lines.append(
            f"| {name} | {workspace['status']} | {workspace['summary']} | {depends} |"
        )
    return "\n".join(lines)


def workspace_body(registry, name):
    workspace = registry["workspaces"][name]
    return (
        f"**Status:** {workspace['status']}{since_suffix(workspace)}\n\n"
        f"{workspace['status_note']}"
    )


def used_vocabulary(registry, names):
    statuses = {registry["workspaces"][n]["status"] for n in names}
    return [s for s in registry["vocabulary"] if s["name"] in statuses]


def agent_body(registry, agent):
    names = workspace_names(agent, registry["workspaces"])
    lines = [f"# Context for {agent['id']}", "", agent["purpose"]]
    for name in names:
        workspace = registry["workspaces"][name]
        lines += [
            "",
            f"## {name} ({workspace['status']}{since_suffix(workspace)})",
            workspace["summary"],
            "",
            workspace["status_note"],
        ]
    lines += ["", "## Status vocabulary"]
    for status in used_vocabulary(registry, names):
        lines.append(f"- **{status['name']}**: {status['definition']}")
    return "\n".join(lines)


def targets(registry):
    out = [
        {
            "kind": "index",
            "key": None,
            "path": "INDEX.md",
            "region": "workspace-index",
        }
    ]
    for name in sorted(registry["workspaces"]):
        workspace = registry["workspaces"][name]
        out.append(
            {
                "kind": "workspace",
                "key": name,
                "path": f"registry/workspaces/{workspace['slug']}/README.md",
                "region": "workspace-status",
            }
        )
    for agent in registry["agents"]:
        out.append(
            {
                "kind": "agent",
                "key": agent["id"],
                "path": f"context/{agent['id']}.md",
                "region": "agent-context",
            }
        )
    return sorted(out, key=lambda t: t["path"])


def body_for(registry, target):
    if target["kind"] == "index":
        return index_body(registry)
    if target["kind"] == "workspace":
        return workspace_body(registry, target["key"])
    agent = next(a for a in registry["agents"] if a["id"] == target["key"])
    return agent_body(registry, agent)


# --------------------------------------------------------------------------- markers


def scan_regions(lines, rel):
    """Map region name to its (start, end) line pairs, or raise Invalid."""
    errors, regions = [], {}
    open_region = None
    for index, line in enumerate(lines):
        number = index + 1
        match = MARKER_RE.match(line)
        if not match:
            continue
        kind, name = match.group(1), match.group(2)
        if kind == "BEGIN":
            if open_region is not None:
                errors.append(
                    f"{rel}:{number}: BEGIN GENERATED:{name} while"
                    f" GENERATED:{open_region[0]} is still open"
                )
                continue
            open_region = (name, index, number)
        else:
            if open_region is None:
                errors.append(
                    f"{rel}:{number}: END GENERATED:{name} has no matching BEGIN"
                )
                continue
            if open_region[0] != name:
                errors.append(
                    f"{rel}:{number}: END GENERATED:{name} closes"
                    f" BEGIN GENERATED:{open_region[0]}"
                )
                open_region = None
                continue
            regions.setdefault(name, []).append((open_region[1], index))
            open_region = None
    if open_region is not None:
        errors.append(
            f"{rel}:{open_region[2]}: BEGIN GENERATED:{open_region[0]} is never closed"
        )
    if errors:
        raise Invalid(errors)
    return regions


def render_text(text, bodies, rel):
    """Return text with every named region body replaced."""
    lines = text.splitlines()
    regions = scan_regions(lines, rel)
    for name in bodies:
        spans = regions.get(name, [])
        if len(spans) != 1:
            raise Invalid(
                [
                    f"{rel}: expected one BEGIN/END GENERATED:{name} pair,"
                    f" found {len(spans)}"
                ]
            )
    for name, body in sorted(
        bodies.items(), key=lambda item: regions[item[0]][0][0], reverse=True
    ):
        start, end = regions[name][0]
        lines[start + 1:end] = body.splitlines()
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- commands


def print_invalid(errors):
    for error in errors:
        print(f"invalid: {error}")


def command_check(root, registry):
    stale, errors = [], []
    for target in targets(registry):
        path = root / target["path"]
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            errors.append(f"{target['path']}: missing")
            continue
        try:
            expected = render_text(text, {target["region"]: body_for(registry, target)},
                                   target["path"])
        except Invalid as exc:
            errors.extend(exc.errors)
            continue
        if expected != text:
            stale.append(target["path"])
    if errors:
        print_invalid(errors)
        return 2
    if stale:
        for path in stale:
            print(f"stale: {path}")
        print(f"check: {len(stale)} of {len(targets(registry))} views are stale; run render")
        return 1
    print(f"check: {len(targets(registry))} views match their records")
    return 0


def command_render(root, registry):
    planned = []
    for target in targets(registry):
        path = root / target["path"]
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            print_invalid([f"{target['path']}: missing"])
            return 2
        try:
            expected = render_text(text, {target["region"]: body_for(registry, target)},
                                   target["path"])
        except Invalid as exc:
            print_invalid(exc.errors)
            return 2
        planned.append((target, path, text, expected))

    written, current = 0, 0
    for target, path, text, expected in planned:
        if expected != text:
            path.write_text(expected, encoding="utf-8")
            print(f"wrote {target['path']}")
            written += 1
        else:
            current += 1
    print(f"render: {written} written, {current} already current")
    return 0


def context_json(registry, agent):
    names = workspace_names(agent, registry["workspaces"])
    return {
        "agent": agent["id"],
        "purpose": agent["purpose"],
        "workspaces": [
            {
                "name": name,
                "status": registry["workspaces"][name]["status"],
                "status_since": registry["workspaces"][name]["status_since"],
                "summary": registry["workspaces"][name]["summary"],
                "status_note": registry["workspaces"][name]["status_note"],
            }
            for name in names
        ],
        "vocabulary": used_vocabulary(registry, names),
    }


def command_context(registry, agent_id, as_json):
    agent = next((a for a in registry["agents"] if a["id"] == agent_id), None)
    if agent is None:
        known = ", ".join(a["id"] for a in registry["agents"])
        print(f"context: no agent named {agent_id!r}; known agents: {known}", file=sys.stderr)
        return 3
    if as_json:
        print(json.dumps(context_json(registry, agent), indent=2))
    else:
        print(agent_body(registry, agent))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="context_registry",
        description="Generate every view from one set of records, and check for drift.",
    )
    ap.add_argument("--root", default=".", help="directory holding the registry (default: cwd)")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="exit non-zero when a record is invalid or a view is stale")
    sub.add_parser("render", help="rewrite every marked region from the records")
    context = sub.add_parser("context", help="print the context assembled for one agent")
    context.add_argument("agent", help="agent id from registry/agents.json")
    context.add_argument("--json", action="store_true", help="machine-readable context")

    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 3

    root = Path(args.root)
    if not root.is_dir():
        print(f"context_registry: {root} is not a directory", file=sys.stderr)
        return 3
    try:
        registry = load_registry(root)
    except Invalid as exc:
        print_invalid(exc.errors)
        return 2

    if args.command == "check":
        return command_check(root, registry)
    if args.command == "render":
        return command_render(root, registry)
    return command_context(registry, args.agent, args.json)


if __name__ == "__main__":
    sys.exit(main())
