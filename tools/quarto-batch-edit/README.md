# quarto-batch-edit

Apply a round of line-level revisions to a Quarto deck or report as one transaction, with
heading-aware placement and an all-or-nothing write.

## The problem

A review round on a rendered deck produces a list of small corrections: delete a clause here,
replace a claim there, rephrase one bullet, tighten a table. Applying them one at a time through an
editor or an agent costs a turn per edit, and the failure mode is worse than the cost. Half a round
can land, the source no longer matches the rendered PDF, and nobody can tell which corrections were
applied.

The other failure is silent misplacement. A phrase such as "Next actions" appears on four slides.
A naive find-and-replace edits the first one and reports success.

This tool takes the whole round as a JSON batch. It resolves every anchor against the heading map
before writing anything, refuses an anchor that matches zero or several places, and applies the
batch in full or not at all.

## How it works

```text
edits.json ──► validate ──► for each edit ──► resolve slide scope
                                              │
                                              ▼
                                     find the anchor in that span
                                              │
                              0 hits ─────────┼───────── 2+ hits
                                 │            │            │
                              failure      place        failure
                                              │
                                              ▼
                                   apply to in-memory buffer
                                              │
                                              ▼
                                  optional external check
                                              │
                         any failure ─────────┴───────── all pass
                              │                              │
                       write nothing, exit 2          write every file
```

The heading map is the addressing layer. It records each heading's index, source line, level and
format visibility, plus every title that appears more than once. An edit can scope itself by title
or by `#index`. A title that resolves to two headings is refused with the indices to use instead.

Format visibility comes from Quarto's `::: {.content-visible when-format="..."}` fences. A deck
that carries parallel revealjs and PDF content needs one edit per fence when a claim appears in
both, and the map's format column is what makes that visible.

## Install

Python 3.10 or later. No packages, no virtual environment.

```bash
git clone https://github.com/MoBattah/EverydayAI.git
cd EverydayAI/tools/quarto-batch-edit
```

Quarto is optional. It is needed only for `--render` and the `render` subcommand.

## Quick start

The sample deck is in `examples/sample-deck/`. Work on a copy so the checked-in example stays
pristine:

```bash
cp -R examples/sample-deck /tmp/deck-demo
cd /tmp/deck-demo
python3 /path/to/quarto_batch_edit.py map index.qmd
python3 /path/to/quarto_batch_edit.py apply index.qmd --edits edits-success.json --dry-run
python3 /path/to/quarto_batch_edit.py apply index.qmd --edits edits-success.json
```

`map` prints:

```text
  #   line  lvl  format    title
  1      11  #    both      Quarterly review
  2      13  ##   both      The bottom line
  ...
  7      36  ##   both      Method
  8      41  ##   typst     Method
  9      46  ##   both      Appendix

  Titles that appear more than once. Scope these by #index:
    Method: #7, #8
    Next actions: #5, #6
```

`apply` prints a before-and-after for every edit and writes both the document and the companion
SCSS file. Run `./demo.sh` to reproduce all three outcomes below in one command.

## The edit specification

```json
{
  "edits": [
    {
      "op": "delete",
      "slide": "The bottom line",
      "text": ", with further work likely in both regions",
      "note": "Drop a clause."
    },
    {
      "op": "replace",
      "slide": "Incident review",
      "text": "watch its dashboards",
      "with": "know which signals mean trouble"
    },
    {
      "op": "rephrase",
      "slide": "The bottom line",
      "text": "Support response time",
      "with": "- **Support response time is the clearest operational signal.** Six of eight regions placed it in their top three."
    },
    {
      "op": "style",
      "file": "theme.scss",
      "text": ".dense table { font-size: 0.515em; }",
      "with": ".dense table { font-size: 0.49em; }"
    }
  ]
}
```

| Field | Required | Meaning |
|---|---|---|
| `op` | yes | `delete`, `replace`, `rephrase` or `style` |
| `text` | yes | The exact, case-sensitive anchor |
| `with` | all but `delete` | The replacement text |
| `slide` | no | A heading title, a unique substring, or `#index` |
| `file` | `style` only | A companion file beside the document |
| `note` | no | Echoed into the report |

Unknown keys are an error. A typo such as `whith` would otherwise apply an edit with no replacement
and look successful.

Placement rules, stated so a refusal is diagnosable:

- An anchor must appear exactly once inside its scope, on a single source line.
- A slide scope matches a title case-insensitively after the `{.class}` attribute is stripped. An
  exact match wins; a unique substring match is accepted; anything else is refused.
- `rephrase` expands its anchor to the containing block. A bullet runs from its marker through any
  more-indented continuation lines. Anything else runs to the surrounding blank lines.
- `delete` respaces the line and repunctuates around the removal. A deletion that would empty the
  line or leave a bare list marker is refused, because dropping a whole bullet should be explicit.

## Failure demonstration

`examples/sample-deck/edits-ambiguous.json` holds one valid edit and one ambiguous edit. The first
edit would succeed on its own. Because the second cannot be placed, neither is written:

```bash
python3 quarto_batch_edit.py apply index.qmd --edits edits-ambiguous.json
```

```text
Would apply 1 edit(s):

  [1] replace · index.qmd:25 · slide Incident review
      - The engineers who own a service watch its dashboards.
      + The engineers who own a service read the support queue.

1 edit(s) could not be placed:

  [2] replace: anchor 'Next actions' appears 2 times in the file (lines 27, 32).
      Lengthen the anchor or scope it to one slide.

Nothing was written. A batch applies in full or not at all.
```

Exit code 2. Both files are byte-for-byte unchanged, which `demo.sh` verifies with `cmp`.

The second failure mode is an external policy refusal. `--check-cmd` takes a command that receives
the new text on stdin and exits non-zero to refuse:

```bash
python3 quarto_batch_edit.py apply index.qmd \
  --edits edits-rejected.json \
  --check-cmd "python3 ../policy_check.py"
```

The edit places cleanly, the checker rejects the word "leverage", and the batch writes nothing. The
checker is a replaceable integration: the editor knows only the stdin and exit-code contract. It
runs on `.md`, `.qmd`, `.txt` and `.html` targets by default; `--check-suffixes` changes that.

## Commands and exit codes

```text
quarto_batch_edit.py map    <document.qmd>
quarto_batch_edit.py apply  <document.qmd> --edits E.json [--dry-run] [--json]
                            [--check-cmd CMD] [--check-suffixes .md,.qmd]
                            [--render] [--open]
quarto_batch_edit.py render <document.qmd> [--open]
```

| Code | Meaning |
|---|---|
| 0 | Every edit applied, or a dry run found every edit placeable |
| 2 | Nothing written: placement or check failure |
| 3 | Usage or edits-file error |
| 4 | Quarto is not on `PATH` |
| 5 | `quarto render` failed |

`--json` prints a machine-readable report with `applied`, `placement_failures` and
`check_failures`. The exit code is unchanged, so an agent can branch on the code and read the
detail from the report.

`--render` runs after a clean apply. If the render fails, the edits remain on disk and the command
returns 5; the write and the render are separate transactions because a render failure is not a
reason to discard a correct source edit.

## Tests

```bash
python3 test_quarto_batch_edit.py
```

The suite covers the heading map, all four edit shapes, ambiguous anchors, duplicate titles across
format fences, strict edit validation, cross-file atomicity, dry runs, replay, the external checker
contract, JSON reporting, and render success, failure and absence. Quarto is stubbed on `PATH`, so
the suite needs neither Quarto nor a network.

## Known limitations

- **Slide-level headings only.** The map reads `#` and `##`. A report that uses `###` subsections
  needs those sections addressed through their parent heading.
- **One line per anchor.** A phrase wrapped across two source lines cannot be matched. Rewrap the
  paragraph first, or use `rephrase` with an anchor that sits on one line.
- **The format fences are not reconciled.** The tool reports which fence a heading lives in; it
  does not infer that a claim in both fences needs two edits.
- **No structural edits.** It does not add, remove or reorder slides, or edit YAML front matter.
- **No layout judgement.** `quarto render` success means the source compiled. Whether a table
  collides with a footer is a visual check.
- **Rendering needs Quarto.** The edit path does not.

## Where this sits in the pipeline

**Assembly.** A revision round is a set of instructions assembled against a document's structure.
The tool's contribution is the assembly discipline: resolve every instruction against the document's
heading map, refuse ambiguity, and commit the batch as one unit so the source and the rendered
artifact cannot disagree about which corrections landed.
