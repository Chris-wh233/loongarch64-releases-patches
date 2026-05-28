#!/usr/bin/env bash
set -euo pipefail

diff_dir="${1:?diff dir is required}"
output_dir="${2:?output dir is required}"
diff_file="${3:?diff file is required}"
project="${4:?project is required}"
version="${5:?version is required}"

mkdir -p "$output_dir"

write_diff() {
  local repo_dir="$1"
  local out_file="$2"
  shift 2

  if [ ! -d "$repo_dir/.git" ]; then
    return 0
  fi

  git -C "$repo_dir" add -N . >/dev/null 2>&1 || true
  git -C "$repo_dir" diff --binary --no-ext-diff -- "$@" > "$out_file" || true
  if [ ! -s "$out_file" ]; then
    rm -f "$out_file"
  fi
}

write_diff "$diff_dir" "$output_dir/$diff_file" .

cat > "$output_dir/manifest.json" <<EOF
{
  "project": "$project",
  "version": "$version",
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "diff_files": [
$(find "$output_dir" -maxdepth 1 -type f \( -name '*.diff' -o -name '*.patch' \) -printf '    "%f",\n' | sed '$ s/,$//')
  ]
}
EOF

echo "Generated diff files for ${project} ${version}:"
find "$output_dir" -maxdepth 1 -type f \( -name '*.diff' -o -name '*.patch' \) -printf '  %f\n' | sort
exit 0
