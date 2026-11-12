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

if [ "$stage" -ge 8 ]; then
  if grep -RInE 'PENDING|TODO|<fill>' docs >/dev/null; then
    echo "placeholder found anywhere under docs/" >&2
    exit 1
  fi

  evidence_list=/tmp/kernelkraft-evidence-list.$$
  awk -F'|' '
    NR > 1 && $0 ~ /^\|/ && $2 !~ /^[[:space:]]*---/ {
      path=$2
      if (path !~ /`/) next
      sub(/^[^`]*`/, "", path)
      sub(/`.*/, "", path)
      if (path ~ /^(logs|results|host|docs|xv6-public|results\.csv)(\/|$)/)
        print path
    }
  ' docs/EVIDENCE_INDEX.md >"$evidence_list"
  evidence_status=0
  while IFS= read -r path; do
    case "$path" in
      *"<br>"*|*","*) continue ;;
    esac
    if [ ! -e "$path" ]; then
      echo "missing evidence path: $path" >&2
      evidence_status=1
    fi
  done <"$evidence_list"
  rm -f "$evidence_list"
  if [ "$evidence_status" -ne 0 ]; then
    exit "$evidence_status"
  fi

  for contributor in "Atharv Dhuvad" "Ridham Shah" "Pranav H Nair"; do
    if ! grep -F "$contributor" docs/CONTRIBUTIONS.md >/dev/null; then
      echo "missing contributor entry: $contributor" >&2
      exit 1
    fi
  done
fi

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

if [ "$stage" -ge 8 ]; then
  archive="${TEAM:-Team_Name}_3.zip"
  archive="dist/$archive"
  if ! unzip -Z1 "$archive" >/tmp/kernelkraft-archive-list.$$ 2>/dev/null; then
    echo "cannot inspect archive: $archive" >&2
    rm -f /tmp/kernelkraft-archive-list.$$
    exit 1
  fi
  if grep -E '(^|/)([^/]+\.(o|d|asm|sym|img|pyc)|kernel|bootblock|fs\.img|dist/|build/|__pycache__)(/|$)' \
      /tmp/kernelkraft-archive-list.$$ >/dev/null; then
    echo "build output found in archive: $archive" >&2
    rm -f /tmp/kernelkraft-archive-list.$$
    exit 1
  fi
  echo
  echo "Stage 8 summary"
  printf '%-28s %s\n' "Documentation placeholders" "PASS"
  printf '%-28s %s\n' "Evidence paths" "PASS"
  printf '%-28s %s\n' "Contributor entries" "PASS"
  printf '%-28s %s\n' "Archive build outputs" "PASS"
  printf '%-28s %s\n' "Archive" "$archive"
  printf '%-28s %s\n' "Packaged files" "$(wc -l < /tmp/kernelkraft-archive-list.$$)"
  rm -f /tmp/kernelkraft-archive-list.$$
fi
