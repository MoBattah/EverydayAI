#!/usr/bin/env bash
# Reproduce the three outcomes against a throwaway copy of the sample deck.
#
#   1. a four-edit batch applies and changes both files
#   2. an ambiguous batch is refused, exit 2, and nothing is written
#   3. a batch that fails the external check is refused, exit 2, and nothing is written
#
# The checked-in example is never modified. Requires python3, diff and cmp.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tool="$here/quarto_batch_edit.py"
sample="$here/examples/sample-deck"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cp -R "$sample" "$work/deck"
cd "$work/deck"

echo "== heading map =="
python3 "$tool" map index.qmd

echo
echo "== 1. four-edit batch, dry run =="
python3 "$tool" apply index.qmd --edits edits-success.json --dry-run

echo
echo "== 1. four-edit batch, applied =="
python3 "$tool" apply index.qmd --edits edits-success.json

echo
echo "== the diff against the checked-in source =="
diff -u "$sample/index.qmd" index.qmd || true
diff -u "$sample/theme.scss" theme.scss || true

echo
echo "== 2. ambiguous batch =="
cp "$sample/index.qmd" index.qmd
cp "$sample/theme.scss" theme.scss
set +e
python3 "$tool" apply index.qmd --edits edits-ambiguous.json
rc=$?
set -e
if [[ "$rc" -ne 2 ]]; then
  echo "FAIL: expected exit 2, got $rc" >&2
  exit 1
fi
cmp "$sample/index.qmd" index.qmd
cmp "$sample/theme.scss" theme.scss
echo "exit 2, both files unchanged"

echo
echo "== 3. external check refusal =="
set +e
python3 "$tool" apply index.qmd --edits edits-rejected.json \
  --check-cmd "python3 '$here/examples/policy_check.py'"
rc=$?
set -e
if [[ "$rc" -ne 2 ]]; then
  echo "FAIL: expected exit 2, got $rc" >&2
  exit 1
fi
cmp "$sample/index.qmd" index.qmd
echo "exit 2, source unchanged"

echo
echo "demo: all three outcomes reproduced; the checked-in example is untouched"
