# deterministic-context

One JSON record per workspace, every Markdown view generated from it, and a check that fails
when a copy drifts. The same records assemble each agent's context, so two agents cannot be
given two versions of the same fact.

## The problem

A status appears in four places: the workspace index, the workspace README, the owning agent's
context file, and the reviewer agent's context file. Someone changes the status in one of them.
The other three now disagree, and nothing in the repository says which one is right. A reader
trusts whichever file they opened first.

The second failure is quieter. A generated file is edited by hand, looks correct, and is
overwritten by the next person who regenerates it. The edit disappears without a conflict.

This demo enforces one rule: an operational fact is recorded once in JSON, and every Markdown
statement of it sits inside a generated region that `check` compares against the records. A
region outside the markers belongs to a person. Prose inside them belongs to the tool.

## How it works

```text
 registry/workspaces/*/project.json ─┐
 registry/vocabulary.json            ├──► validate ──► render each view in memory
 registry/agents.json                ┘                  │
                                                        ▼
                                        compare with the file on disk
                                          │                    │
                                       equal                differs
                                          │                    │
                                     check: 0            check: 1, names the view
```

Each view is a Markdown file with one marked region:

```markdown
# Alpha

<!-- BEGIN GENERATED:workspace-status -->
**Status:** Active since 2026-01-15

First synthetic workspace; used throughout the walkthrough
<!-- END GENERATED:workspace-status -->

## Notes

Hand-written prose belongs outside the markers.
```

`render` replaces the body and leaves everything outside the markers untouched. `check` renders
the same body in memory and compares bytes, so a stale view is reported with the file that needs
regenerating.

The tool never creates a file. A new workspace needs its `README.md` and its agent needs a
context file, each carrying the marker pair, before `render` will fill them. A missing file is an
error. Generated text never lands somewhere nobody chose.

`context` recomputes an agent's context from the records instead of reading the generated file,
so the command answers what the agent should receive even while a view is stale.

## The records

```text
example/
├── INDEX.md                       generated table of workspaces
├── registry/
│   ├── vocabulary.json            the closed set of statuses
│   ├── agents.json                which workspaces each agent receives
│   └── workspaces/
│       ├── alpha/
│       │   ├── project.json       the record
│       │   └── README.md          generated status block plus hand prose
│       └── beta/
│           ├── project.json
│           └── README.md
└── context/
    ├── alpha-agent.md             assembled from Alpha
    ├── beta-agent.md              assembled from Beta
    └── portfolio-agent.md         assembled from every workspace
```

### project.json

```json
{
  "version": 1,
  "name": "Beta",
  "status": "Paused",
  "status_since": "2026-02-02",
  "status_note": "Paused while the Alpha schema settles",
  "summary": "A synthetic reporting workspace that consumes Alpha output",
  "depends_on": ["Alpha"]
}
```

| Field | Rules |
|---|---|
| `name` | Matches the directory name, ignoring case. Unique. |
| `status` | One of the names in `vocabulary.json`. |
| `status_since` | An ISO date, or `null`. |
| `status_note` | One line, 160 characters at most, no `\|`, no trailing newline. |
| `summary` | One line, 160 characters at most, no `\|`. |
| `depends_on` | Known workspace names, no self-reference, no duplicates, no cycles. |

An unknown key is an error. A field nothing reads is how a record starts to rot.

### vocabulary.json

The statuses and their definitions. The set is closed: a record with a status outside it is
invalid, and an agent's context prints only the definitions for the statuses its workspaces hold.

### agents.json

```json
{
  "version": 1,
  "agents": [
    {"id": "alpha-agent", "purpose": "Owns the Alpha workspace and its two pipelines",
     "workspaces": ["Alpha"]},
    {"id": "portfolio-agent", "purpose": "Reviews every workspace",
     "workspaces": ["*"]}
  ]
}
```

`id` is lowercase letters, digits and hyphens, and is unique. `workspaces` is a list of record
names, or `["*"]` for every workspace. The wildcard stands alone so the breadth is stated once.

## Install

Python 3.10 or later. No packages.

```bash
git clone https://github.com/MoBattah/EverydayAI.git
cd EverydayAI/demos/deterministic-context
```

## Quick start

```bash
python3 context_registry.py --root example check
python3 context_registry.py --root example render
python3 context_registry.py --root example context alpha-agent
```

`check` on the checked-in example:

```text
check: 6 views match their records
```

A slice of the generated index:

```text
<!-- BEGIN GENERATED:workspace-index -->
| Workspace | Status | Summary | Depends on |
|---|---|---|---|
| Alpha | Active | A synthetic analytics workspace with two pipelines | none |
| Beta | Paused | A synthetic reporting workspace that consumes Alpha output | Alpha |
<!-- END GENERATED:workspace-index -->
```

`context alpha-agent`:

```text
# Context for alpha-agent

Owns the Alpha workspace and its two pipelines

## Alpha (Active since 2026-01-15)
A synthetic analytics workspace with two pipelines

First synthetic workspace; used throughout the walkthrough

## Status vocabulary
- **Active**: Work is moving and the record is current
```

`--json` prints the same facts as an object with `agent`, `purpose`, `workspaces` and
`vocabulary`.

`demo.sh` copies the example to a temp directory and reproduces the full cycle:

```bash
./demo.sh
```

It checks the data, renders, wipes every generated body and proves a second render reproduces
the same bytes, prints one agent's context, changes a status to show drift and recovery, then
sets an invalid status and breaks a marker to show both refusals.

## Failure demonstration

**Drift.** Change Alpha's status without regenerating:

```text
stale: INDEX.md
stale: context/alpha-agent.md
stale: context/portfolio-agent.md
stale: registry/workspaces/alpha/README.md
check: 4 of 6 views are stale; run render
```

Exit code 1. The Beta views are absent because Beta's record did not change, which is the
useful part: the report names exactly what the edit touched.

**Invalid data.** Set the status to `Banana`:

```text
invalid: registry/workspaces/alpha/project.json: status 'Banana' is not in the vocabulary
```

Exit code 2, and `render` refuses to write anything.

**A broken marker.** Delete the closing marker from a generated file:

```text
invalid: context/beta-agent.md:1: BEGIN GENERATED:agent-context is never closed
```

Exit code 2. A duplicated pair, a mismatched name, a stray END and a missing marker line are all
invalid, and each message names the file and line.

## Commands and exit codes

```text
context_registry.py [--root DIR] check
context_registry.py [--root DIR] render
context_registry.py [--root DIR] context AGENT [--json]
```

`--root` defaults to the current directory and must contain `registry/vocabulary.json`.

| Code | Meaning |
|---|---|
| 0 | Everything matches |
| 1 | A view is stale; run `render` |
| 2 | A record, a marker or JSON syntax is invalid; nothing was written |
| 3 | Usage error, missing root, or unknown agent |

`check` reports data errors before staleness. When both exist, the data errors win, because
rendering invalid records would spread the error into every view.

`render` prints each file it writes and a final `render: N written, M already current`. Running
it twice in a row reports `0 written`.

## Tests

```bash
python3 test_context_registry.py
```

The suite runs 92 checks against copies of the checked-in example under the system temp
directory. It covers the shipped example, every generated view, agent scoping including the
wildcard, JSON output, byte-for-byte determinism after wiping the bodies, sorted output for a
workspace added after the existing ones, drift detection and repair, hand prose preservation,
every marker failure, every validation rule, render's refusal to write on invalid data, the
read-only behavior of `check` and `context`, and the exit codes.

## Known limitations

- **One marker pair per view.** Each generated file needs exactly one matching pair. A
  duplicated, mismatched or unclosed pair is an error rather than a guess.
- **No orphan scan.** Removing an agent or a workspace leaves its generated file behind. The
  tool checks the files the records name, so delete the file in the same change.
- **No file creation.** A new record needs its README and context file with the marker pair
  first. `render` fills regions; it does not choose paths.
- **Plain text cells.** Values are rendered as written. Markdown inside a summary would render
  as Markdown, so the validation forbids pipes and newlines and leaves the rest to the author.
- **One root per run.** Registries do not nest. A second registry is a second invocation.
- **POSIX assumptions.** The suite runs on macOS and Linux. Windows was not tested.

## Where this sits in the pipeline

**Storage.** The question is where a fact lives and what else is generated from it. Each
workspace fact lives in one JSON record; the index, the README status block and every agent's
context are projections of that record, and `check` fails when a projection and its record
disagree. Because the agent context is assembled from the same records, the storage rule and the
assembly rule share one source of truth: an agent receives what the record says, and a stale view
is visible before anyone acts on it.
