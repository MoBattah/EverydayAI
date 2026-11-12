#!/usr/bin/env bash
# Reconstruct the state of a throwaway repository, then prove the run wrote nothing.
#
#   1. a full report: worktrees with verdicts, unmerged and unpushed branches,
#      landed commits, a checkpoint, and a task provider
#   2. the same facts as JSON
#   3. a fresh fetch makes the landed section change
#   4. a path that is not a repository exits 1
#   5. a file-by-file hash of the repository, including .git, is identical before
#      and after a full run
#
# Local paths only. No network, no GitHub account, no gh. Requires python3 and git.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tool="$here/agent_continuity.py"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME="Demo"
export GIT_AUTHOR_EMAIL="demo@example.com"
export GIT_COMMITTER_NAME="Demo"
export GIT_COMMITTER_EMAIL="demo@example.com"
export GIT_TERMINAL_PROMPT=0

# A bare origin, a clone that does the work, and a second clone that plays the
# colleague who lands a commit while the first clone is not looking.
git init --bare -q "$work/origin.git"
git init -q "$work/repo"
cd "$work/repo"
git remote add origin "$work/origin.git"
printf 'Quarterly report draft.\n' > report.md
git add -A
git commit -q -m "land a first report"
git branch -M main
git push -q -u origin main
git -C "$work/origin.git" symbolic-ref HEAD refs/heads/main
git symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main

# A checkpoint directory, written the way a working session would leave it and
# committed so the primary checkout is clean.
mkdir -p checkpoints
today="$(date +%Y-%m-%d)"
printf '# session\n\n**Session focus:** finish the tables section\n' \
  > "checkpoints/${today}-0900.md"
printf '# session\n\n**Session focus:** start the appendix\n' \
  > "checkpoints/2025-11-03-1600.md"
git add checkpoints
git commit -q -m "record the session checkpoint"
git push -q origin main

git clone -q "$work/origin.git" "$work/partner"
printf 'Appendix.\n' > "$work/partner/appendix.md"
git -C "$work/partner" add -A
git -C "$work/partner" commit -q -m "add the appendix"
git -C "$work/partner" push -q origin main

# A feature branch, pushed once and then taken one commit further.
git checkout -q -b feature/tables
printf 'Table 1.\n' > tables.md
git add -A
git commit -q -m "draft the tables section"
git push -q -u origin feature/tables
printf 'Table 2.\n' >> tables.md
git add -A
git commit -q -m "add the second table"
git checkout -q main

# Three worktrees: one abandoned, one dirty, one with month-old unmerged work.
mkdir -p "$work/trees"
git worktree add -q "$work/trees/scratch" -b wt-scratch main
git worktree add -q "$work/trees/hotfix" -b wt-hotfix main
printf 'half a fix\n' > "$work/trees/hotfix/note.txt"
git worktree add -q "$work/trees/old" -b wt-old main
old="$(python3 -c 'import datetime; print((datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%dT12:00:00"))')"
printf 'old experiment\n' > "$work/trees/old/experiment.txt"
git -C "$work/trees/old" add -A
GIT_AUTHOR_DATE="$old" GIT_COMMITTER_DATE="$old" \
  git -C "$work/trees/old" commit -q -m "an experiment from last month"

# A checkpoint directory and a task provider, the two optional inputs.
cat > "$work/tasks.sh" <<'SH'
#!/bin/sh
echo '- [ ] Send the tables draft to the editor'
echo '- [ ] Decide whether the appendix ships in this release'
SH
chmod +x "$work/tasks.sh"

run() {
  python3 "$tool" --repo . --checkpoints . --tasks-cmd "sh $work/tasks.sh" --no-net
}

echo "== 1. full report =="
run

echo
echo "== 2. the same facts as JSON =="
python3 "$tool" --repo . --no-net --json | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(json.dumps({
    "default_branch": d["default_branch"],
    "head": d["head"],
    "worktrees": {w.get("branch", "detached"): w["verdict"] for w in d["worktrees"]},
    "unpushed": d["branches"]["unpushed"],
    "landed_before_fetch": d["landed"]["total"],
}, indent=2))
'

echo
echo "== 3. the landed section is a fetch behind, and says so =="
before="$(python3 "$tool" --repo . --no-net --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["landed"]["total"])')"
git fetch -q origin
after="$(python3 "$tool" --repo . --no-net --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["landed"]["total"])')"
printf 'landed commits before the fetch: %s\nlanded commits after the fetch:  %s\n' "$before" "$after"
[[ "$before" -eq 0 && "$after" -eq 1 ]] || {
  echo "FAIL: expected 0 then 1, got $before then $after" >&2
  exit 1
}

echo
echo "== 4. a path that is not a repository =="
mkdir -p "$work/plain"
set +e
python3 "$tool" --repo "$work/plain"
rc=$?
set -e
printf 'exit %s\n' "$rc"
[[ "$rc" -eq 1 ]] || {
  echo "FAIL: expected exit 1, got $rc" >&2
  exit 1
}

echo
echo "== 5. read-only proof =="
cat > "$work/hash-tree.py" <<'PY'
import hashlib, os, sys

root = sys.argv[1]
digest = hashlib.sha256()
for dirpath, dirnames, filenames in os.walk(root):
    dirnames.sort()
    for name in sorted(filenames):
        path = os.path.join(dirpath, name)
        rel = os.path.relpath(path, root)
        digest.update(rel.encode() + b"\0")
        if os.path.islink(path):
            digest.update(b"L" + os.readlink(path).encode())
            continue
        with open(path, "rb") as fh:
            digest.update(fh.read())
print(digest.hexdigest())
PY
before_hash="$(python3 "$work/hash-tree.py" "$work/repo")"
run > /dev/null
after_hash="$(python3 "$work/hash-tree.py" "$work/repo")"
printf 'before: %s\nafter:  %s\n' "$before_hash" "$after_hash"
[[ "$before_hash" == "$after_hash" ]] || {
  echo "FAIL: the report changed a file under the repository" >&2
  exit 1
}

echo
echo "demo: every section printed, the fetch boundary held, and the repository is byte-identical"
