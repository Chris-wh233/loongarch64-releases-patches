#!/usr/bin/env bash
set -euo pipefail

source_dir="${1:?source dir is required}"
output_dir="${2:?output dir is required}"
project="${3:?project is required}"
version="${4:?version is required}"

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

write_diff "$source_dir" "$output_dir/source.diff" .

if [ -d "${HOME}/.conan/.git" ]; then
  write_diff "${HOME}/.conan" "$output_dir/conan-home.diff" . ":(exclude)data"
fi

if [ -d "${HOME}/.conan/data/.git" ]; then
  write_diff "${HOME}/.conan/data" "$output_dir/conan-data.diff" .
fi

if [ -d "${HOME}/.cargo/registry/src" ]; then
  while IFS= read -r cargo_repo; do
    name="$(basename "$cargo_repo")"
    write_diff "$cargo_repo" "$output_dir/cargo-registry-${name}.diff" .
  done < <(find "${HOME}/.cargo/registry/src" -mindepth 2 -maxdepth 2 -type d -name 'cty-*' 2>/dev/null)
fi

cat > "$output_dir/manifest.json" <<EOF
{
  "project": "$project",
  "version": "$version",
  "generated_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "diff_files": [
$(find "$output_dir" -maxdepth 1 -type f -name '*.diff' -printf '    "%f",\n' | sed '$ s/,$//')
  ]
}
EOF

echo "Generated diff files for ${project} ${version}:"
find "$output_dir" -maxdepth 1 -type f -name '*.diff' -printf '  %f\n' | sort
exit 0

