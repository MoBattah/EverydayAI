#!/usr/bin/env python3
"""Apply a batch of line-level edits to a Quarto document, then optionally render it.

Three subcommands:

    map    <document.qmd>                  print the heading map used to scope edits
    apply  <document.qmd> --edits E.json   place and apply every edit, or none
    render <document.qmd> [--open]         quarto render, optionally open the PDF

The placement contract: an anchor that does not resolve to exactly one occurrence
inside its scope is reported back with the candidates. Nothing is written until
every edit in the batch has placed and passed the optional external check.

Exit codes:
    0  every edit applied (or a dry run found every edit placeable)
    2  nothing written: an edit failed to place or failed the external check
    3  usage or edits-file error
    4  quarto is not on PATH
    5  quarto render failed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

OPS = ("delete", "replace", "rephrase", "style")
EDIT_KEYS = {"op", "text", "with", "slide", "file", "note"}

# Suffixes the external checker inspects by default. A style edit to any other
# file skips the check, because a prose checker has nothing to say about SCSS.
DEFAULT_CHECK_SUFFIXES = (".md", ".qmd", ".txt", ".html")

HEADING_RE = re.compile(r"^(#{1,2})\s+(.*?)\s*$")
LIST_MARKER_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+")
FENCE_OPEN_RE = re.compile(r'^:::+\s*\{\s*\.content-visible\s+when-format="([^"]+)"')
FENCE_ANY_RE = re.compile(r"^:::")
BARE_MARKER_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s*$")

CHECK_TIMEOUT = 30


# --------------------------------------------------------------------------
# Heading map
# --------------------------------------------------------------------------


@dataclass
class Heading:
    index: int  # 1-based ordinal among all headings in the file
    line: int  # 1-based line number of the heading itself
    level: int  # 1 for a section title slide, 2 for a content slide
    title: str  # heading text with any {.class} attribute stripped
    raw: str  # heading text as written
    fmt: str  # revealjs, typst, or both
    start: int  # 1-based first line of the slide body
    end: int  # 1-based last line of the slide body, inclusive


def strip_attrs(title: str) -> str:
    """Drop a trailing pandoc attribute block, so '## X {.dense}' matches 'X'."""
    return re.sub(r"\s*\{[^{}]*\}\s*$", "", title).strip()


def build_map(lines: list[str]) -> list[Heading]:
    """Ordinal, line span and format visibility for every heading in the file.

    Format visibility comes from the enclosing ::: content-visible fence. A
    heading outside any such fence is reported as 'both'.
    """
    headings: list[Heading] = []
    fmt_stack: list[str] = []
    depth = 0
    in_code = False

    for i, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        opened = FENCE_OPEN_RE.match(line)
        if opened:
            depth += 1
            fmt_stack.append(opened.group(1))
            continue
        if FENCE_ANY_RE.match(line):
            if line.strip().startswith(":::") and "{" in line:
                depth += 1
                fmt_stack.append("")
            elif depth:
                depth -= 1
                fmt_stack.pop()
            continue

        m = HEADING_RE.match(line)
        if not m:
            continue
        active = [f for f in fmt_stack if f]
        headings.append(
            Heading(
                index=len(headings) + 1,
                line=i,
                level=len(m.group(1)),
                title=strip_attrs(m.group(2)),
                raw=m.group(2),
                fmt=active[-1] if active else "both",
                start=i + 1,
                end=len(lines),
            )
        )

    for a, b in zip(headings, headings[1:]):
        a.end = b.line - 1
    return headings


def format_map(headings: list[Heading]) -> str:
    rows = ["  #   line  lvl  format    title"]
    for h in headings:
        rows.append(
            f"  {h.index:<3} {h.line:>5}  {'#' * h.level:<3}  {h.fmt:<8}  {h.title}"
        )
    dupes: dict[str, list[int]] = {}
    for h in headings:
        dupes.setdefault(h.title, []).append(h.index)
    repeated = {t: ix for t, ix in dupes.items() if len(ix) > 1}
    if repeated:
        rows.append("")
        rows.append("  Titles that appear more than once. Scope these by #index:")
        for title, ix in sorted(repeated.items()):
            rows.append(f"    {title}: {', '.join('#' + str(i) for i in ix)}")
    return "\n".join(rows)


# --------------------------------------------------------------------------
# Edit placement
# --------------------------------------------------------------------------


@dataclass
class Edit:
    n: int  # 1-based position in the batch, for reporting
    op: str
    text: str
    replacement: str | None = None
    slide: str | None = None
    target: str | None = None  # companion file, style op only
    note: str | None = None


@dataclass
class Failure:
    edit: Edit
    reason: str


@dataclass
class Applied:
    edit: Edit
    path: Path
    line: int
    before: str
    after: str


@dataclass
class Batch:
    applied: list[Applied] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)


def load_edits(path: Path) -> list[Edit]:
    """Read and validate an edits file. Unknown keys are an error, not a silent typo."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        unknown = set(raw) - {"edits", "_comment"}
        if unknown:
            raise ValueError(f"unknown top-level key(s) {sorted(unknown)}; expected 'edits'")
        raw = raw.get("edits", [])
    if not isinstance(raw, list):
        raise ValueError("the edits file must hold a list, or an object with an 'edits' list")
    if not raw:
        raise ValueError("the edits file holds no edits")

    edits: list[Edit] = []
    for i, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"edit {i}: expected an object, got {type(item).__name__}")
        unknown = set(item) - EDIT_KEYS
        if unknown:
            raise ValueError(f"edit {i}: unknown key(s) {sorted(unknown)}")
        op = item.get("op")
        if op not in OPS:
            raise ValueError(f"edit {i}: op must be one of {', '.join(OPS)}, got {op!r}")
        if not item.get("text"):
            raise ValueError(f"edit {i}: 'text' is required and names the anchor")
        if op == "delete" and "with" in item:
            raise ValueError(f"edit {i}: op 'delete' takes no 'with' field")
        if op != "delete" and item.get("with") is None:
            raise ValueError(f"edit {i}: op '{op}' requires a 'with' field")
        if op == "style" and not item.get("file"):
            raise ValueError(f"edit {i}: op 'style' requires a 'file' naming the companion file")
        if op == "style" and item.get("slide"):
            raise ValueError(f"edit {i}: 'slide' is not valid with op 'style'; scope the anchor with 'text'")
        if op != "style" and item.get("file"):
            raise ValueError(f"edit {i}: 'file' is only valid with op 'style'")
        if item.get("slide") is not None and not isinstance(item["slide"], str):
            raise ValueError(f"edit {i}: 'slide' must be a string")
        edits.append(
            Edit(
                n=i,
                op=op,
                text=item["text"],
                replacement=item.get("with"),
                slide=item.get("slide"),
                target=item.get("file"),
                note=item.get("note"),
            )
        )
    return edits


def resolve_scope(edit: Edit, headings: list[Heading]) -> tuple[int, int] | Failure:
    """Return the 1-based inclusive line span the anchor is searched within."""
    if not edit.slide:
        return (1, 10**9)

    key = edit.slide.strip()
    if key.startswith("#") and key[1:].strip().isdigit():
        want = int(key[1:].strip())
        for h in headings:
            if h.index == want:
                return (h.line, h.end)
        return Failure(edit, f"no heading with index #{want}; run 'map' to see the range")

    matches = [h for h in headings if h.title.lower() == key.lower()]
    if not matches:
        loose = [h for h in headings if key.lower() in h.title.lower()]
        if len(loose) == 1:
            return (loose[0].line, loose[0].end)
        if not loose:
            return Failure(edit, f"no slide titled {key!r}; run 'map' to see the titles")
        listed = ", ".join(f"#{h.index} {h.title!r}" for h in loose)
        return Failure(edit, f"slide {key!r} matches {len(loose)} headings loosely: {listed}")
    if len(matches) > 1:
        listed = ", ".join(f"#{h.index} (line {h.line})" for h in matches)
        return Failure(
            edit,
            f"slide {key!r} appears {len(matches)} times: {listed}. Scope by index, "
            f'for example "slide": "#{matches[0].index}"',
        )
    return (matches[0].line, matches[0].end)


def find_occurrences(lines: list[str], text: str, span: tuple[int, int]) -> list[int]:
    """1-based line numbers inside span whose line contains text."""
    lo, hi = span
    hits = []
    for i in range(max(1, lo), min(len(lines), hi) + 1):
        if text in lines[i - 1]:
            hits.append(i)
    return hits


def tidy(line: str) -> str:
    """Repair the spacing a phrase removal leaves behind."""
    line = re.sub(r"[ \t]{2,}", " ", line)
    line = re.sub(r"\s+([,.;:!?\)\]])", r"\1", line)
    line = re.sub(r"([\(\[])\s+", r"\1", line)
    return line.rstrip() if line.strip() else line


def block_span(lines: list[str], anchor_line: int) -> tuple[int, int]:
    """The bullet or paragraph containing anchor_line, as a 1-based inclusive span.

    A bullet runs from its marker through any more-indented continuation lines.
    Anything else runs to the surrounding blank lines.
    """
    i = anchor_line
    start = i
    while start > 1 and lines[start - 1].strip() and not LIST_MARKER_RE.match(lines[start - 1]):
        if not lines[start - 2].strip():
            break
        start -= 1
        if LIST_MARKER_RE.match(lines[start - 1]):
            break

    m = LIST_MARKER_RE.match(lines[start - 1])
    end = start
    if m:
        indent = len(m.group(1))
        while end < len(lines):
            nxt = lines[end]
            if not nxt.strip():
                break
            nm = LIST_MARKER_RE.match(nxt)
            if nm and len(nm.group(1)) <= indent:
                break
            if not nm and (len(nxt) - len(nxt.lstrip())) <= indent:
                break
            end += 1
    else:
        while end < len(lines) and lines[end].strip():
            end += 1
    return (start, end)


def plan_edit(
    edit: Edit,
    lines: list[str],
    headings: list[Heading],
) -> tuple[list[str], Applied] | Failure:
    """Return the file's new lines plus a record, or the reason placement failed."""
    scope = resolve_scope(edit, headings)
    if isinstance(scope, Failure):
        return scope

    hits = find_occurrences(lines, edit.text, scope)
    where = f"slide {edit.slide!r}" if edit.slide else "the file"
    if not hits:
        return Failure(edit, f"anchor {edit.text!r} does not appear in {where}")
    if len(hits) > 1:
        listed = ", ".join(str(h) for h in hits)
        return Failure(
            edit,
            f"anchor {edit.text!r} appears {len(hits)} times in {where} "
            f"(lines {listed}). Lengthen the anchor or scope it to one slide.",
        )

    at = hits[0]
    out = list(lines)
    before = lines[at - 1]

    if edit.op == "delete":
        line = before.replace(edit.text, "", 1)
        after = tidy(line)
        if not after.strip():
            return Failure(
                edit,
                f"deleting {edit.text!r} would empty line {at}. Delete the whole "
                f"bullet with a rephrase, or shorten the anchor.",
            )
        if BARE_MARKER_RE.match(after):
            return Failure(
                edit,
                f"deleting {edit.text!r} would leave a bare list marker at line {at}. "
                f"To drop the whole bullet, use a rephrase.",
            )
        out[at - 1] = after
        return out, Applied(edit, Path(), at, before, after)

    if edit.op in ("replace", "style"):
        after = before.replace(edit.text, edit.replacement, 1)
        out[at - 1] = after
        return out, Applied(edit, Path(), at, before, after)

    # rephrase: swap the whole bullet or paragraph the anchor sits in
    start, end = block_span(lines, at)
    before_block = "\n".join(lines[start - 1 : end])
    new_block = edit.replacement.rstrip("\n").split("\n")
    out[start - 1 : end] = new_block
    return out, Applied(edit, Path(), start, before_block, "\n".join(new_block))


# --------------------------------------------------------------------------
# Optional external check
# --------------------------------------------------------------------------


def run_check(command: str, text: str, cwd: Path) -> str | None:
    """Return the checker's refusal reason for this text, or None when it passes.

    The contract is deliberately narrow: the command receives the candidate text on
    stdin and exits non-zero to refuse. Its stderr becomes the reason. A checker that
    cannot run is a refusal, because a silent skip would turn a gate into decoration.
    """
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return f"the check command is not parseable: {exc}"
    if not argv:
        return "the check command is empty"
    try:
        proc = subprocess.run(
            argv, input=text, cwd=cwd, capture_output=True, text=True, timeout=CHECK_TIMEOUT
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"the check command could not run: {exc}"
    if proc.returncode == 0:
        return None
    reason = (proc.stderr or proc.stdout).strip()
    return reason or f"the check command exited {proc.returncode}"


def check_suffixes(raw: str | None) -> set[str]:
    if not raw:
        return set(DEFAULT_CHECK_SUFFIXES)
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        out.add(part if part.startswith(".") else f".{part}")
    return out


# --------------------------------------------------------------------------
# apply
# --------------------------------------------------------------------------


def run_apply(args) -> int:
    document = Path(args.document).resolve()
    if not document.is_file():
        print(f"quarto-batch-edit: no such document: {document}", file=sys.stderr)
        return 3

    try:
        edits = load_edits(Path(args.edits))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"quarto-batch-edit: {exc}", file=sys.stderr)
        return 3

    suffixes = check_suffixes(args.check_suffixes)
    check = args.check_cmd

    # Working copy per touched file, so every edit sees the earlier ones.
    buffers: dict[Path, list[str]] = {}
    originals: dict[Path, str] = {}

    def buffer_for(path: Path) -> list[str]:
        if path not in buffers:
            raw = path.read_text(encoding="utf-8")
            originals[path] = raw
            buffers[path] = raw.split("\n")
        return buffers[path]

    batch = Batch()
    check_failures: list[Failure] = []

    for edit in edits:
        path = document if not edit.target else (document.parent / edit.target)
        if not path.is_file():
            batch.failures.append(Failure(edit, f"no such file: {path}"))
            continue

        lines = buffer_for(path)
        headings = build_map(lines) if path.suffix == ".qmd" else []
        planned = plan_edit(edit, lines, headings)
        if isinstance(planned, Failure):
            batch.failures.append(planned)
            continue

        new_lines, record = planned
        record.path = path

        if check and path.suffix in suffixes:
            candidate = edit.replacement if edit.op != "delete" else record.after
            reason = run_check(check, candidate, document.parent)
            if reason:
                check_failures.append(Failure(edit, reason))
                continue

        buffers[path] = new_lines
        batch.applied.append(record)

    ok = not batch.failures and not check_failures

    if args.json:
        print(json.dumps(report_json(batch, check_failures, args.dry_run, ok), indent=2))
    else:
        report(batch, check_failures, args.dry_run, ok)

    if not ok:
        if not args.json:
            print("\nNothing was written. A batch applies in full or not at all.")
        return 2
    if args.dry_run:
        if not args.json:
            print("\nDry run. Nothing was written.")
        return 0

    for path, lines in buffers.items():
        path.write_text("\n".join(lines), encoding="utf-8")
    if not args.json:
        print(f"\nWrote {len(buffers)} file(s).")

    if args.render:
        rc = render(document, open_output=args.open)
        if rc != 0:
            return rc
    return 0


def report_json(batch: Batch, check_failures: list[Failure], dry_run: bool, ok: bool) -> dict:
    return {
        "ok": ok,
        "dry_run": dry_run,
        "applied": [
            {
                "n": rec.edit.n,
                "op": rec.edit.op,
                "file": str(rec.path),
                "line": rec.line,
                "before": rec.before,
                "after": rec.after,
                "note": rec.edit.note,
            }
            for rec in batch.applied
        ],
        "placement_failures": [
            {"n": f.edit.n, "op": f.edit.op, "reason": f.reason} for f in batch.failures
        ],
        "check_failures": [
            {"n": f.edit.n, "op": f.edit.op, "reason": f.reason} for f in check_failures
        ],
    }


def report(batch: Batch, check_failures: list[Failure], dry_run: bool, ok: bool) -> None:
    verb = "Would apply" if (dry_run or not ok) else "Applied"
    if batch.applied:
        print(f"{verb} {len(batch.applied)} edit(s):\n")
        for rec in batch.applied:
            head = f"  [{rec.edit.n}] {rec.edit.op} · {rec.path.name}:{rec.line}"
            if rec.edit.slide:
                head += f" · slide {rec.edit.slide}"
            print(head)
            for line in rec.before.split("\n"):
                print(f"      - {line.strip()[:150]}")
            for line in rec.after.split("\n"):
                print(f"      + {line.strip()[:150]}")
            if rec.edit.note:
                print(f"      note: {rec.edit.note}")
            print()

    if batch.failures:
        print(f"{len(batch.failures)} edit(s) could not be placed:\n")
        for f in batch.failures:
            print(f"  [{f.edit.n}] {f.edit.op}: {f.reason}\n")

    if check_failures:
        print(f"{len(check_failures)} edit(s) placed but failed the external check:\n")
        for f in check_failures:
            print(f"  [{f.edit.n}] {f.edit.op}:")
            for line in f.reason.split("\n"):
                print(f"      {line}")
            print()


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def open_command() -> str | None:
    if sys.platform == "darwin":
        return "open"
    if shutil.which("xdg-open"):
        return "xdg-open"
    return None


def render(document: Path, open_output: bool = False) -> int:
    if shutil.which("quarto") is None:
        print("quarto-batch-edit: quarto is not on PATH", file=sys.stderr)
        return 4
    print(f"\nRendering {document.name} ...")
    proc = subprocess.run(
        ["quarto", "render", document.name],
        cwd=document.parent,
        capture_output=True,
        text=True,
    )
    tail = (proc.stdout + proc.stderr).strip().split("\n")
    for line in tail[-12:]:
        print(f"  {line}")
    if proc.returncode != 0:
        print(f"quarto-batch-edit: quarto render failed, exit {proc.returncode}", file=sys.stderr)
        return 5

    outputs = [p for p in (document.with_suffix(".html"), document.with_suffix(".pdf")) if p.is_file()]
    print("\n  outputs: " + (", ".join(str(p) for p in outputs) or "none reported"))
    if open_output:
        opener = open_command()
        if opener is None:
            print("  no opener found; open the output by hand")
        else:
            for p in outputs:
                if p.suffix == ".pdf":
                    subprocess.run([opener, str(p)], check=False)
    return 0


# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="quarto-batch-edit", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("map", help="print the heading map")
    m.add_argument("document")

    a = sub.add_parser("apply", help="place and apply a batch of edits")
    a.add_argument("document")
    a.add_argument("--edits", required=True, help="path to the edits JSON")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument(
        "--check-cmd",
        help="external checker: receives the new text on stdin, exits non-zero to refuse",
    )
    a.add_argument(
        "--check-suffixes",
        help="comma-separated suffixes the checker inspects "
        f"(default: {','.join(DEFAULT_CHECK_SUFFIXES)})",
    )
    a.add_argument("--json", action="store_true", help="print a machine-readable report")
    a.add_argument("--render", action="store_true", help="quarto render after a clean apply")
    a.add_argument("--open", action="store_true", help="open the rendered PDF")

    r = sub.add_parser("render", help="quarto render the document")
    r.add_argument("document")
    r.add_argument("--open", action="store_true")

    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 3

    if args.cmd == "map":
        document = Path(args.document)
        if not document.is_file():
            print(f"quarto-batch-edit: no such document: {document}", file=sys.stderr)
            return 3
        print(format_map(build_map(document.read_text(encoding="utf-8").split("\n"))))
        return 0

    if args.cmd == "render":
        return render(Path(args.document).resolve(), open_output=args.open)

    return run_apply(args)


if __name__ == "__main__":
    sys.exit(main())
