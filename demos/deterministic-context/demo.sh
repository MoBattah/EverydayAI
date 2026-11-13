#!/usr/bin/env bash
# Reproduce the record-to-view cycle on a throwaway copy of the example registry.
#
#   1. check passes on the checked-in data
#   2. render is a no-op, because every view is already current
#   3. wiping every generated body and rendering again reproduces the same bytes
#   4. context prints the assembled context for one agent
#   5. a changed record makes check exit 1 and names every stale view
#   6. a status outside the vocabulary makes check exit 2
#   7. a broken marker pair makes check exit 2 and render refuses to write
#
# The checked-in example is never modified. Requires python3.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tool="$here/context_registry.py"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cp -R "$here/example" "$work/registry"
cd "$work/registry"

hash_views() {
  python3 - "$1" <<'PY'
import hashlib, pathlib, sys

root = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(root.rglob("*.md")):
    digest.update(str(path.relative_to(root)).encode() + b"\0")
    digest.update(path.read_bytes())
print(digest.hexdigest())
PY
}

blank_views() {
  python3 - "$tool" <<'PY'
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(sys.argv[1]).parent))
import context_registry as cr

for path in pathlib.Path(".").rglob("*.md"):
    out, inside = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        marker = cr.MARKER_RE.match(line)
        if marker:
            out.append(line)
            inside = marker.group(1) == "BEGIN"
            continue
        if not inside:
            out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

echo "== 1. check =="
python3 "$tool" --root . check

echo
echo "== 2. render on a current registry =="
python3 "$tool" --root . render

echo
echo "== 3. the views are a pure function of the records =="
before="$(hash_views .)"
blank_views
echo "wiped every generated body"
python3 "$tool" --root . render
after="$(hash_views .)"
printf 'before: %s\nafter:  %s\n' "$before" "$after"
[[ "$before" == "$after" ]] || {
  echo "FAIL: rendering the same records produced different bytes" >&2
  exit 1
}

echo
echo "== 4. assembled context for alpha-agent =="
python3 "$tool" --root . context alpha-agent

echo
echo "== 5. a changed record is detected =="
python3 - <<'PY'
import json, pathlib

path = pathlib.Path("registry/workspaces/alpha/project.json")
data = json.loads(path.read_text(encoding="utf-8"))
data.update(status="Paused", status_since="2026-03-01",
            status_note="Paused while the schema is rewritten")
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
set +e
python3 "$tool" --root . check
rc=$?
set -e
printf 'exit %s\n' "$rc"
[[ "$rc" -eq 1 ]] || {
  echo "FAIL: expected exit 1, got $rc" >&2
  exit 1
}
python3 "$tool" --root . render
python3 "$tool" --root . check

echo
echo "== 6. a status outside the vocabulary is refused =="
python3 - <<'PY'
import json, pathlib

path = pathlib.Path("registry/workspaces/alpha/project.json")
data = json.loads(path.read_text(encoding="utf-8"))
data.update(status="Banana")
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
PY
set +e
python3 "$tool" --root . check
rc=$?
set -e
printf 'exit %s\n' "$rc"
[[ "$rc" -eq 2 ]] || {
  echo "FAIL: expected exit 2, got $rc" >&2
  exit 1
}
cp "$here/example/registry/workspaces/alpha/project.json" \
   "registry/workspaces/alpha/project.json"
python3 "$tool" --root . render > /dev/null
python3 "$tool" --root . check

echo
echo "== 7. a broken marker is refused, and render writes nothing =="
python3 - <<'PY'
import pathlib

path = pathlib.Path("context/beta-agent.md")
lines = path.read_text(encoding="utf-8").splitlines()
path.write_text("\n".join(l for l in lines if "END GENERATED" not in l) + "\n",
                encoding="utf-8")
PY
before="$(hash_views .)"
set +e
python3 "$tool" --root . check
rc=$?
set -e
printf 'exit %s\n' "$rc"
[[ "$rc" -eq 2 ]] || {
  echo "FAIL: expected exit 2, got $rc" >&2
  exit 1
}
set +e
python3 "$tool" --root . render
rc=$?
set -e
printf 'render exit %s\n' "$rc"
[[ "$rc" -eq 2 ]] || {
  echo "FAIL: expected render exit 2, got $rc" >&2
  exit 1
}
after="$(hash_views .)"
[[ "$before" == "$after" ]] || {
  echo "FAIL: a refused render changed a file" >&2
  exit 1
}

echo
echo "demo: check, render, determinism, drift recovery, and both refusals reproduced"
