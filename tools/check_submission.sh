#!/bin/sh
set -eu

if [ "$#" -ne 1 ] || ! printf '%s' "$1" | grep -Eq '^[0-9]+$'; then
  echo "usage: $0 <stage>" >&2
  exit 2
fi
stage=$1
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)

required=""
add_required() { required="$required $1"; }
add_required docs/JOURNAL.md
add_required docs/DESIGN.md
add_required docs/PARAMS.md
add_required docs/CONTRIBUTIONS.md
[ "$stage" -lt 1 ] || {
  add_required docs/SYSCALLS.md
  add_required docs/TEST_TABLE.md
  add_required docs/EVIDENCE_INDEX.md
}
[ "$stage" -lt 2 ] || {
  add_required docs/LIMITATIONS.md
  add_required docs/REPORT_NOTES.md
  add_required docs/VIVA.md
}
[ "$stage" -lt 3 ] || add_required logs/audit.jsonl
[ "$stage" -ge 7 ] && add_required results/results.csv

cd "$root"
for file in $required; do
  if [ ! -s "$file" ]; then
    echo "missing or empty required file: $file" >&2
    exit 1
  fi
  if grep -nE 'TODO|<fill>' "$file" >/dev/null; then
    echo "placeholder found in required file: $file" >&2
    exit 1
  fi
done

if [ "$stage" -ge 1 ] && awk -F'|' -v stage="$stage" '
  /^[|]/ && $0 !~ /ID[[:space:]]*\|/ {
    gsub(/[[:space:]]/, "", $2)
    if ($2 ~ /^[0-9]+$/ && $2 <= stage && $6 ~ /PENDING/) found=1
  }
  END { exit found ? 0 : 1 }
' docs/TEST_TABLE.md; then
  echo "pending test row is due by stage $stage" >&2
  exit 1
fi

if [ "$stage" -lt 8 ] && ! find docs/gdb -type f -print -quit 2>/dev/null | grep -q .; then
  echo "warning: no docs/gdb evidence file before stage 8" >&2
fi

"$root/tools/make_zip.sh"
