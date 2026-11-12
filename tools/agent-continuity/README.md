# agent-continuity

Reconstruct a repository's working state in one read-only call: where HEAD is, what is dirty,
which worktrees hold unmerged work, what landed upstream, which pull requests are open, how old
the newest checkpoint is, and what tasks are waiting.

## The problem

An agent that opens a repository after other agents have worked in it spends its first calls
rediscovering the same facts. It runs `git status` and sees a clean tree, while a worktree two
directories away holds the only copy of a fix. It reads local `main` and misses a commit that
landed on the remote an hour ago. It lists branches and cannot tell which ones were pushed. The
facts exist in Git and in the issue tracker, and the cost of gathering them is paid again in every
session that starts.

The failure mode is worse than the cost. A report assembled by hand is trusted as a summary while
it silently omits the one worktree that matters, or states a pull request is passing when its
checks are still running.

This command gathers the facts once, from Git and from `gh`, and states the boundary of what it
knows. It never fetches, so it labels the landed section as a view of the last fetch. It never
writes, so a session can run it before deciding anything.

## How it works

```text
                    ┌──────────────────────────────┐
                    │ resolve the repository root   │
                    └──────────────┬───────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
 default branch             worktrees, in parallel      branch state
 origin/HEAD first          status, last commit,        unmerged into the
 then remote refs           ahead/behind, verdict       default ref
 then current branch                                        │
        │                          │                          │
        └──────────────────────────┼──────────────────────────┘
                                   │
        ┌──────────────────────────┼──────────────────────────┐
        │                          │                          │
        ▼                          ▼                          ▼
 landed commits             pull requests (gh)         checkpoint and tasks
 HEAD..origin/main          checks rolled up           optional inputs
```

Every external call has a timeout. A section that cannot be answered is reported as unavailable,
with the reason, and the remaining sections still print.

### The read-only guarantee

The tool runs only commands that read: `rev-parse`, `symbolic-ref`, `worktree list`, `status`,
`log`, `rev-list`, `for-each-ref`, `branch --no-merged` and `remote get-url`. It does not fetch.
Every Git call sets `GIT_OPTIONAL_LOCKS=0`, which stops even `git status` from refreshing the
index. `demo.sh` hashes every file under the repository, including `.git`, before and after a full
run and compares the two.

### Default branch resolution

`origin/HEAD` is authoritative when it is set. Otherwise the tool checks conventional names
against the remote refs, then falls back to the current branch. The report states which source
answered, so a guess is visible as a guess.

### Worktree verdicts

Each worktree is inspected in parallel and given one label:

| Verdict | Meaning |
|---|---|
| `clean` | The primary checkout, with no uncommitted changes |
| `dirty` | Uncommitted changes in the worktree |
| `stale` | Clean, holds unmerged commits, and no commit in `--stale-days` (default 14) |
| `active` | Clean, holds unmerged commits, and has a recent commit |
| `abandoned` | Clean and holds nothing the default branch lacks, so removing it loses no work |
| `missing` | The path in the worktree registry no longer exists |

The verdicts are a heuristic, stated in the report so a reader can discount them.

## Install

Python 3.10 or later and Git. No packages.

```bash
git clone https://github.com/MoBattah/EverydayAI.git
cd EverydayAI/tools/agent-continuity
```

`gh` is optional. It is used only for the pull request section, and only when the remote is on
GitHub.

## Quick start

Run it against the repository you are already in:

```bash
python3 tools/agent-continuity/agent_continuity.py --repo .
```

`demo.sh` builds a throwaway repository with a bare origin, a feature branch, three worktrees, a
checkpoint and a task provider, then prints the report and proves the run wrote nothing:

```bash
./demo.sh
```

An abridged report:

```text
agent-continuity · /home/you/work/repo
remote /home/you/work/origin.git
default branch main (origin/HEAD), comparing against origin/main
HEAD 769b7df on main, tree clean

Worktrees (4): 1 abandoned, 1 clean, 1 dirty, 1 stale
-----------------------------------------------------
  dirty = uncommitted changes. stale = clean, unmerged, no commit in 14 days.
  abandoned = clean and holds nothing the default branch lacks.
  clean = the primary checkout; it is not removable.
  main
      /home/you/work/repo
      clean · +0/-0 vs origin/main · 0d old
      last: record the session checkpoint
  wt-hotfix
      /home/you/work/trees/hotfix
      dirty · 1 changed · +0/-0 vs origin/main · 0d old
      last: record the session checkpoint
  wt-old
      /home/you/work/trees/old
      stale · +1/-0 vs origin/main · 30d old
      last: an experiment from last month
  wt-scratch
      /home/you/work/trees/scratch
      abandoned · +0/-0 vs origin/main · 0d old
      last: record the session checkpoint

Local branches unmerged into origin/main (2)
--------------------------------------------
  Local refs only. 1 remote-only branch is also unmerged and is not listed.
  feature/tables
  wt-old

Unpushed local branches (2)
---------------------------
  feature/tables · ahead 1
  wt-old · no upstream, holds unmerged commits

On origin/main but not in your HEAD (0)
---------------------------------------
  Reported by committer; git does not record who pushed.
  nothing; your HEAD has everything on the default branch
  Reflects the last fetch. This command does not fetch.

Open pull requests
------------------
  skipped: --no-net

Newest checkpoint
-----------------
  /home/you/work/repo/checkpoints/2026-11-12-0900.md
  0.0 days old
  focus: finish the tables section

Open tasks (2)
--------------
  - [ ] Send the tables draft to the editor
  - [ ] Decide whether the appendix ships in this release
```

## The report sections

**Worktrees.** Local worktrees from `git worktree list`, with the branch, path, last commit,
count of changes, and ahead/behind against the default ref. A worktree whose directory was deleted
is reported as `missing` instead of disappearing from the list.

**Unmerged branches.** Local branches whose commits are not on the default ref, and local branches
holding commits their upstream does not have. A branch with no upstream is listed only when it
holds unmerged commits, which keeps merged leftovers out of the section. Remote-only branches
appear as a count, because a large repository can carry hundreds.

**Landed.** Commits on the default ref that local `HEAD` does not contain. The section reports the
committer, because Git does not record who pushed. It reflects the last fetch by design.

**Pull requests.** Open pull requests through `gh pr list`, with the head branch, author, draft
flag, and a rollup of check states: `passing`, `failing`, `running`, `no checks`, or `mixed`. When
`gh` is absent or not authenticated, the section says so and the rest of the report prints.

**Newest checkpoint.** With `--checkpoints DIR`, the tool walks for directories named `checkpoints`
and picks the newest `YYYY-MM-DD*.md` file by file name. File names are used for ordering because
a clone stamps every file with the same modification time. The age comes from the date in the name,
with the modification time as a fallback, and a `**Session focus:**` line is lifted into the report.

**Tasks.** With `--tasks-cmd CMD`, the command runs with the repository as its working directory
and one task per line on stdout. Exit 0 means the lines are the list. Any other exit is reported as
`unavailable` with the first line of stderr, because an empty list would read as nothing owed.

## Commands and exit codes

```text
agent_continuity.py [--repo PATH] [--full] [--no-net] [--no-tasks]
                    [--checkpoints DIR] [--tasks-cmd CMD]
                    [--stale-days N] [--json]
```

| Flag | Effect |
|---|---|
| `--repo PATH` | Repository to inspect. Defaults to the current directory |
| `--full` | Print every list instead of truncating at 12 worktrees, 12 branches, 10 commits or 10 pull requests |
| `--no-net` | Skip the GitHub call |
| `--no-tasks` | Skip the task provider even when one is configured |
| `--checkpoints DIR` | Search under `DIR` for the newest checkpoint |
| `--tasks-cmd CMD` | Run `CMD` and treat one line of stdout as one task |
| `--stale-days N` | Age at which a clean, unmerged worktree is called stale. Default 14 |
| `--json` | Print the report as JSON |

| Code | Meaning |
|---|---|
| 0 | The report printed. Individual sections may still be unavailable, and the JSON says why |
| 1 | The path is not a Git repository, or does not exist |
| 2 | Usage error |

`--json` emits one object. The keys are `repo`, `remote`, `github`, `default_branch`, `head`,
`worktrees`, `branches`, `landed`, `pull_requests`, `checkpoints` and `tasks`. Every optional
section carries a `status` of `ok`, `skipped`, `unavailable`, `missing` or `none`. A section that
could not be read carries a `reason`, so a caller can distinguish "nothing found" from "could not
look".

```json
{
  "default_branch": {"name": "main", "source": "origin/HEAD", "ref": "origin/main"},
  "head": {"branch": "feature/tables", "sha": "769b7df", "dirty": 1},
  "worktrees": [
    {"branch": "feature/tables", "path": "/home/you/work/repo", "dirty": 1,
     "ahead": 1, "behind": 0, "verdict": "dirty", "primary": true}
  ],
  "branches": {"unmerged": ["feature/tables"], "unpushed": [{"name": "feature/tables", "why": "ahead 1"}]},
  "landed": {"commits": [], "total": 0},
  "pull_requests": {"status": "skipped", "reason": "--no-net", "items": []}
}
```

## Failure demonstration

A path that is not a repository prints one line and exits 1, with no partial report:

```bash
python3 agent_continuity.py --repo /tmp
```

```text
agent-continuity: /tmp is not inside a git repository, or git is not installed
```

Exit code 1. The error names the path that was tried.

The other failures are section-local and do not stop the report. `demo.sh` reproduces the
not-a-repository exit. To see a section fail while the rest prints, make the task provider exit
non-zero:

```bash
python3 agent_continuity.py --tasks-cmd "false"
```

The tasks section reports `unavailable` with the provider's own message, and every other section
still prints.

The landed section is deliberately a view of the last fetch. `demo.sh` pushes a commit from a
second clone, runs the report to show zero landed commits, fetches, and runs it again to show one.
The tool does not close that gap on its own.

## Tests

```bash
python3 test_agent_continuity.py
```

The suite runs 82 checks. Every test builds a throwaway bare origin and clone under the system
temp directory, with `GIT_CONFIG_GLOBAL` pointed at `/dev/null` and a synthetic committer identity.
`gh` is stubbed on `PATH`, so no account or network access is required.

The suite covers URL parsing for GitHub and non-GitHub remotes, default branch resolution with and
without `origin/HEAD`, dirty counts, unmerged and unpushed branches, remote-only branch counts, the
no-fetch boundary, all six worktree verdicts, detached and missing worktrees, the stale threshold,
PR check rollups including a failing `gh`, checkpoint selection by file name, the task provider
contract and its failure path, the JSON schema, truncation and `--full`, exit codes, and a
file-by-file and `git status` comparison that proves a full run changes nothing.

## Known limitations

- **A view of the last fetch.** The tool does not fetch, so the landed section and ahead/behind
  counts are only as current as the last fetch. This is a deliberate trade: a read-only command
  that fetches is not read-only.
- **Local branches only.** Remote-only branches appear only as a count. A repository with hundreds
  of remote branches would otherwise dominate the report.
- **Checkpoints need the directory name.** The walk finds directories named `checkpoints`. A
  differently named folder must be moved or linked.
- **Line-based tasks.** The provider contract is one line per task on stdout. There is no
  structured task schema, so a provider that needs fields should format its own line.
- **Open pull requests only.** The `gh` call asks for open PRs, ten by default. It does not list
  reviews, mergeability, or closed work.
- **Heuristic verdicts.** `stale` and `abandoned` depend on commit age and ahead/behind counts.
  They are advice about what to inspect, not a decision about what to delete.
- **POSIX assumptions.** The suite runs on macOS and Linux. Windows was not tested.
- **A worktree on another machine is invisible.** The registry lists paths; a path that is missing
  here is reported as `missing`, and this tool cannot inspect the machine that holds it.

## Where this sits in the pipeline

**Inception.** A session begins by establishing what is already true: the branch, the dirty state,
the unmerged work, the upstream commits, the open reviews. This tool turns that step into one
bounded, read-only call with stated limits, so the first decision a session makes rests on facts it
can point to.
