#!/usr/bin/env bash
set -euo pipefail

main_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
only_project="${1:-}"
requested_version="${2:-}"

if [ -n "$requested_version" ] && [ -z "$only_project" ]; then
  echo "A version requires a project name." >&2
  exit 2
fi

if [ -z "$only_project" ]; then
  export DIFF_PACKAGE_SELECTOR="__all__"
fi

projects="$(python3 - "$main_root/projects.json" "$only_project" <<'PY'
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
only = sys.argv[2]
found = False
for item in data["projects"]:
    if only and item["name"] != only:
        continue
    if not item.get("patched") or (not only and item.get("skip_build", False)):
        continue
    files = item.get("required_diff_files", [])
    print("\t".join((item["name"], item["ci_repo"], " ".join(files))))
    found = True
if only and not found:
    raise SystemExit(f"unknown patched project: {only}")
PY
)"

if [ -z "$projects" ]; then
  echo "No projects selected."
  exit 0
fi

while IFS=$'\t' read -r project ci_repo expected_files; do
  if [ -n "$requested_version" ]; then
    version="$requested_version"
  else
    version="$(gh api "repos/${ci_repo}/releases/latest" --jq '.tag_name')"
  fi

  version_dir="${main_root}/diff-patches/${project}/${version}"
  complete=true
  if [ ! -f "${version_dir}/manifest.json" ]; then
    complete=false
  fi
  for file in $expected_files; do
    if [ ! -s "${version_dir}/${file}" ]; then
      complete=false
    fi
  done
  if [ "$complete" = true ]; then
    echo "${project} ${version} already generated; skipping."
    continue
  fi

  echo "Generating diffs for ${project} ${version}"
  "${main_root}/scripts/generate_project_diff.sh" "$project" "$version"
done <<< "$projects"
