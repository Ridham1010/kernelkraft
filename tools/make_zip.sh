#!/bin/sh
set -eu

if ! git rev-parse --verify baseline >/dev/null 2>&1; then
  echo "make_zip.sh: required git tag 'baseline' was not found" >&2
  exit 1
fi

out_dir=dist
archive="${out_dir}/${TEAM:-Team_Name}_3.zip"
mkdir -p "$out_dir"
list_file=$(mktemp)
trap 'rm -f "$list_file"' EXIT

git diff --name-only --diff-filter=AM baseline HEAD >"$list_file"
git ls-files --others --exclude-standard >>"$list_file"
sort -u "$list_file" |
  grep -Ev '(^|/)([^/]+\.o|[^/]+\.d|[^/]+\.asm|[^/]+\.sym|kernel|bootblock|fs\.img|dist/|build/)' |
  grep -Ev '(^|/)(__pycache__|\.pytest_cache)(/|$)' >"${list_file}.filtered" || true
mv "${list_file}.filtered" "$list_file"

if [ ! -s "$list_file" ]; then
  echo "make_zip.sh: no added or modified files to package" >&2
  exit 1
fi

rm -f "$archive"
(
  cd "$(git rev-parse --show-toplevel)"
  zip -q "$archive" -@ <"$list_file"
)
echo "Packaged files:"
cat "$list_file"
echo "Total size: $(du -h "$archive" | awk '{print $1}')"
