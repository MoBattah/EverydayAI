#!/usr/bin/env python3
"""Tests for quarto_batch_edit.py.

Run: python3 tools/quarto-batch-edit/test_quarto_batch_edit.py

Every test builds its own temporary document. The sample deck in examples/ is never
modified; demo.sh is what exercises that copy.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import quarto_batch_edit as de  # noqa: E402

DECK = """---
title: "Sample"
format:
  revealjs:
    theme: [default, theme.scss]
---

::: {.content-visible when-format="revealjs"}

## The bottom line

- **A first baseline**, with further work likely at both ends.
- QA is the clearest signal across the portfolio.

:::

# 1 · Headline

## Incident response {.smaller}

The engineers who own a service watch its dashboards.

## Next actions

1. Talk to each engineering leader.
2. Request tiered read-only access.

## Next actions

- The same title again, on purpose.

## Method

Web version.

::: {.content-visible when-format="typst"}
## Method

PDF version.
:::

```
## Not a heading

This line is inside a fenced code block.
```
"""

PASSED = 0
FAILED = 0


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
    """Run main() in-process, returning (exit code, stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = de.main(argv)
    return rc, buf.getvalue()


def deck_lines():
    return DECK.split("\n")


def plan(op, text, **kw):
    lines = deck_lines()
    headings = de.build_map(lines)
    edit = de.Edit(
        n=1,
        op=op,
        text=text,
        replacement=kw.get("replacement"),
        slide=kw.get("slide"),
        target=kw.get("target"),
    )
    return de.plan_edit(edit, lines, headings), lines


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def executable(path: Path, body: str) -> Path:
    write(path, body)
    path.chmod(0o755)
    return path


def main() -> int:
    print("heading map")
    headings = de.build_map(deck_lines())
    check("finds every heading", [h.title for h in headings], [
        "The bottom line", "1 · Headline", "Incident response", "Next actions", "Next actions",
        "Method", "Method",
    ])
    check("strips the {.smaller} attribute", headings[2].title, "Incident response")
    check("reads the content-visible fence", headings[0].fmt, "revealjs")
    check("a heading outside a fence is both", headings[1].fmt, "both")
    check("a heading in a typst fence is typst", headings[6].fmt, "typst")
    check("levels are right", [h.level for h in headings], [2, 1, 2, 2, 2, 2, 2])
    check("spans do not overlap", headings[0].end < headings[1].line, True)
    check("a heading inside a code fence is ignored", [h.title for h in headings].count("Not a heading"), 0)
    rendered = de.format_map(headings)
    check_true("the map names repeated titles", "Next actions: #4, #5" in rendered)
    check_true("the map names both Method headings", "Method: #6, #7" in rendered)

    print("\ndelete")
    res, _ = plan("delete", ", with further work likely at both ends", slide="The bottom line")
    check_true("delete places", not isinstance(res, de.Failure))
    check("delete tidies the line", res[1].after, "- **A first baseline**.")

    res, _ = plan("delete", "QA is the clearest signal across the portfolio.")
    check_true("refuses a delete that empties the bullet",
               isinstance(res, de.Failure) and "bare list marker" in res.reason)

    res, _ = plan("delete", "The engineers who own a service watch its dashboards.")
    check_true("refuses a delete that empties a paragraph",
               isinstance(res, de.Failure) and "would empty line" in res.reason)

    print("\nreplace")
    res, _ = plan("replace", "watch its dashboards", replacement="know what signals mean trouble",
                  slide="Incident response")
    check("replace swaps the phrase", res[1].after,
          "The engineers who own a service know what signals mean trouble.")

    print("\nrephrase")
    res, _ = plan("rephrase", "QA is the clearest",
                  replacement="- QA is the clearest portfolio-wide signal, named by nine of ten.",
                  slide="The bottom line")
    check("rephrase swaps the whole bullet", res[1].after,
          "- QA is the clearest portfolio-wide signal, named by nine of ten.")

    res, _ = plan("rephrase", "The engineers who own",
                  replacement="Service owners read their own dashboards daily.")
    check("rephrase swaps a paragraph", res[1].after,
          "Service owners read their own dashboards daily.")

    nested = "## Actions\n\n- Parent item\n  - Child item with the anchor\n- Sibling item\n"
    lines = nested.split("\n")
    edit = de.Edit(n=1, op="rephrase", text="Child item", replacement="  - Replaced child")
    res = de.plan_edit(edit, lines, de.build_map(lines))
    check("rephrase replaces a nested bullet only", res[1].after, "  - Replaced child")
    check("and leaves the sibling", "\n".join(res[0]).count("Sibling item"), 1)

    print("\nambiguity is reported, never guessed")
    res, _ = plan("replace", "Next actions", replacement="What happens next")
    check_true("a duplicate title is refused",
               isinstance(res, de.Failure) and "appears 2 times" in res.reason)

    res, _ = plan("replace", "the same title again", replacement="x", slide="Next actions")
    check_true("a duplicate slide scope is refused with indices",
               isinstance(res, de.Failure) and "Scope by index" in res.reason)

    res, _ = plan("replace", "The same title again", replacement="x", slide="#5")
    check_true("scoping by index resolves it", not isinstance(res, de.Failure))

    res, _ = plan("replace", "Web version", replacement="Changed", slide="Method")
    check_true("a title shared across format fences is refused",
               isinstance(res, de.Failure) and "appears 2 times" in res.reason)

    res, _ = plan("replace", "PDF version", replacement="Changed", slide="#7")
    check("scoping to the typst fence changes only that fence", res[1].after, "Changed.")

    res, _ = plan("delete", "a phrase that is not in the deck")
    check_true("a missing anchor is refused",
               isinstance(res, de.Failure) and "does not appear" in res.reason)

    res, _ = plan("delete", "Talk to", slide="No Such Slide")
    check_true("an unknown slide is refused",
               isinstance(res, de.Failure) and "no slide titled" in res.reason)

    print("\nedits-file validation")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        good = d / "good.qmd"
        good.write_text(DECK, encoding="utf-8")

        def load(payload, name="e.json"):
            p = d / name
            p.write_text(json.dumps(payload), encoding="utf-8")
            return de.load_edits(p)

        for label, payload, needle in [
            ("unknown op", [{"op": "rename", "text": "x"}], "op must be"),
            ("missing text", [{"op": "delete"}], "'text' is required"),
            ("delete with a replacement", [{"op": "delete", "text": "x", "with": "y"}], "takes no 'with'"),
            ("replace without a replacement", [{"op": "replace", "text": "x"}], "requires a 'with'"),
            ("style without a file", [{"op": "style", "text": "x", "with": "y"}], "requires a 'file'"),
            ("style with a slide scope", [{"op": "style", "file": "t.scss", "slide": "X", "text": "x",
                                           "with": "y"}], "'slide' is not valid"),
            ("file on a non-style op", [{"op": "replace", "text": "x", "with": "y", "file": "z"}],
             "only valid with op 'style'"),
            ("unknown key", [{"op": "delete", "text": "x", "whith": "y"}], "unknown key"),
            ("empty batch", [], "holds no edits"),
            ("non-list", {"edits": "nope"}, "must hold a list"),
        ]:
            try:
                load(payload)
                check_true(f"{label} is refused", False)
            except ValueError as exc:
                check_true(f"{label} is refused", needle in str(exc), f"({exc})")

        try:
            load({"edits": [{"op": "delete", "text": "x"}], "_comment": ["ok"]})
            check_true("a top-level _comment is allowed", True)
        except ValueError as exc:
            check_true("a top-level _comment is allowed", False, str(exc))

        rc, out = run(["apply", str(good), "--edits", str(d / "missing.json")])
        check("a missing edits file exits 3", rc, 3)

    print("\natomicity and the external check, end to end")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        deck = d / "sample.qmd"
        deck.write_text(DECK, encoding="utf-8")
        theme = d / "theme.scss"
        theme.write_text(".dense table { font-size: 0.515em; }\n", encoding="utf-8")
        edits = d / "edits.json"

        def write_edits(items):
            edits.write_text(json.dumps(items), encoding="utf-8")

        write_edits([
            {"op": "replace", "slide": "Incident response", "text": "watch its dashboards",
             "with": "know what signals mean trouble"},
            {"op": "delete", "slide": "The bottom line", "text": "a phrase that is absent"},
        ])
        rc, out = run(["apply", str(deck), "--edits", str(edits)])
        check("a batch with one unplaceable edit returns 2", rc, 2)
        check("and writes nothing", deck.read_text(encoding="utf-8"), DECK)
        check_true("and names the failure", "does not appear" in out)

        write_edits([
            {"op": "replace", "slide": "Incident response", "text": "watch its dashboards",
             "with": "know what signals mean trouble"},
            {"op": "style", "file": "theme.scss", "text": "font-size: 0.515em",
             "with": "font-size: 0.49em"},
        ])
        before = deck.read_text(encoding="utf-8")
        before_theme = theme.read_text(encoding="utf-8")
        rc, out = run(["apply", str(deck), "--edits", str(edits), "--dry-run"])
        check("a dry run returns 0", rc, 0)
        check("and writes no document", deck.read_text(encoding="utf-8"), before)
        check("and writes no companion file", theme.read_text(encoding="utf-8"), before_theme)
        check_true("and reports what it would do", "Would apply 2 edit(s)" in out)

        rc, _ = run(["apply", str(deck), "--edits", str(edits)])
        check("a clean batch returns 0", rc, 0)
        check_true("the document changed",
                   "know what signals mean trouble" in deck.read_text(encoding="utf-8"))
        check_true("the companion file changed", "0.49em" in theme.read_text(encoding="utf-8"))

        before = deck.read_text(encoding="utf-8")
        rc, _ = run(["apply", str(deck), "--edits", str(edits)])
        check("replaying the same batch returns 2", rc, 2)
        check("and leaves the first application in place", deck.read_text(encoding="utf-8"), before)

        # A valid document edit plus a failing companion edit: neither may land.
        deck.write_text(DECK, encoding="utf-8")
        theme.write_text(".dense table { font-size: 0.515em; }\n", encoding="utf-8")
        write_edits([
            {"op": "replace", "slide": "Incident response", "text": "watch its dashboards",
             "with": "read the queue"},
            {"op": "style", "file": "theme.scss", "text": "font-size: 0.515em",
             "with": "font-size: 0.40em"},
            {"op": "delete", "text": "not present anywhere"},
        ])
        rc, _ = run(["apply", str(deck), "--edits", str(edits)])
        check("a cross-file batch fails as a unit", rc, 2)
        check("the document is untouched", deck.read_text(encoding="utf-8"), DECK)
        check("the companion file is untouched",
              theme.read_text(encoding="utf-8"), ".dense table { font-size: 0.515em; }\n")

        # The external checker.
        checker = executable(d / "check.py", f"""#!{sys.executable}
import sys
text = sys.stdin.read()
if "leverage" in text:
    print("hype word: leverage", file=sys.stderr)
    sys.exit(1)
sys.exit(0)
""")
        deck.write_text(DECK, encoding="utf-8")
        write_edits([{"op": "replace", "slide": "Incident response", "text": "watch its dashboards",
                      "with": "leverage the dashboards"}])
        rc, out = run(["apply", str(deck), "--edits", str(edits), "--check-cmd", str(checker)])
        check("a checker refusal returns 2", rc, 2)
        check("and writes nothing", deck.read_text(encoding="utf-8"), DECK)
        check_true("and prints the checker's reason", "hype word" in out)

        rc, _ = run(["apply", str(deck), "--edits", str(edits), "--check-cmd",
                     str(checker), "--no-such-flag"])
        check("an unknown flag exits 3", rc, 3)

        write_edits([{"op": "replace", "slide": "Incident response", "text": "watch its dashboards",
                      "with": "read the queue"}])
        rc, _ = run(["apply", str(deck), "--edits", str(edits), "--check-cmd",
                     str(checker)])
        check("a passing check lets the batch through", rc, 0)

        deck.write_text(DECK, encoding="utf-8")
        rc, out = run(["apply", str(deck), "--edits", str(edits), "--check-cmd",
                       str(d / "no-such-checker.py")])
        check("a checker that cannot run refuses the batch", rc, 2)
        check("and writes nothing", deck.read_text(encoding="utf-8"), DECK)

        deck.write_text(DECK, encoding="utf-8")
        write_edits([{"op": "style", "file": "theme.scss", "text": "0.515em", "with": "0.50em"}])
        rc, _ = run(["apply", str(deck), "--edits", str(edits), "--check-cmd",
                     str(checker)])
        check("a non-prose suffix skips the checker by default", rc, 0)
        check_true("and the style edit lands", "0.50em" in theme.read_text(encoding="utf-8"))

        theme.write_text(".dense table { font-size: 0.515em; }\n", encoding="utf-8")
        rc, _ = run(["apply", str(deck), "--edits", str(edits), "--check-cmd",
                     str(checker), "--check-suffixes", ".scss"])
        check("--check-suffixes can include a style file", rc, 0)

        # JSON reporting.
        deck.write_text(DECK, encoding="utf-8")
        write_edits([{"op": "replace", "slide": "Incident response", "text": "watch its dashboards",
                      "with": "read the queue"}])
        rc, out = run(["apply", str(deck), "--edits", str(edits), "--json"])
        data = json.loads(out)
        check("a JSON report returns 0", rc, 0)
        check("and reports one applied edit", len(data["applied"]), 1)
        check("and no failures", data["placement_failures"], [])
        check("and ok is true", data["ok"], True)

        deck.write_text(DECK, encoding="utf-8")
        write_edits([{"op": "delete", "text": "not present"}])
        rc, out = run(["apply", str(deck), "--edits", str(edits), "--json"])
        data = json.loads(out)
        check("a failing JSON report returns 2", rc, 2)
        check("and ok is false", data["ok"], False)
        check("and carries the reason", "does not appear" in data["placement_failures"][0]["reason"], True)

    print("\nrendering is optional and its absence is explicit")
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        deck = d / "sample.qmd"
        deck.write_text(DECK, encoding="utf-8")
        edits = d / "edits.json"
        edits.write_text(json.dumps([
            {"op": "replace", "slide": "Incident response", "text": "watch its dashboards",
             "with": "read the queue"},
        ]), encoding="utf-8")

        empty_bin = d / "empty-bin"
        empty_bin.mkdir()
        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = str(empty_bin)
            rc, _ = run(["apply", str(deck), "--edits", str(edits), "--render"])
            check("no quarto exits 4", rc, 4)
        finally:
            os.environ["PATH"] = old_path

        stub = executable(d / "bin" / "quarto", "#!/bin/sh\necho '<html></html>' > sample.html\nexit 0\n")
        deck.write_text(DECK, encoding="utf-8")
        try:
            os.environ["PATH"] = f"{stub.parent}{os.pathsep}{old_path}"
            rc, out = run(["apply", str(deck), "--edits", str(edits), "--render"])
            check("a successful render exits 0", rc, 0)
            check_true("and reports the output", "sample.html" in out)
        finally:
            os.environ["PATH"] = old_path

        deck.write_text(DECK, encoding="utf-8")
        bad = executable(d / "bad-bin" / "quarto", "#!/bin/sh\necho 'boom' >&2\nexit 1\n")
        try:
            os.environ["PATH"] = f"{bad.parent}{os.pathsep}{old_path}"
            rc, _ = run(["apply", str(deck), "--edits", str(edits), "--render"])
            check("a failed render exits 5", rc, 5)
        finally:
            os.environ["PATH"] = old_path

        rc, _ = run(["map", str(d / "missing.qmd")])
        check("map on a missing document exits 3", rc, 3)

    print(f"\n{PASSED} passed, {FAILED} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
