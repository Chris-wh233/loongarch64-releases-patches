#!/usr/bin/env bash
set -euo pipefail

main_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
only_project="${1:-}"

if [ -z "$only_project" ]; then
  export DIFF_PACKAGE_SELECTOR="__all__"
fi

projects="$(python3 - "$main_root/projects.json" "$only_project" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
only = sys.argv[2]
for item in data["projects"]:
    if not item.get("patched"):
        continue
    if only:
        if item["name"] == only:
            print(item["name"])
    elif not item.get("skip_build", False):
        print(item["name"])
PY
)"

for project in $projects; do
  tag="$(gh api "repos/loongarch64-releases/${project}/releases/latest" --jq '.tag_name')"
  version="$tag"

  if [ -f "${main_root}/diff-patches/${project}/${version}/manifest.json" ]; then
    echo "${project} ${version} already generated; skipping."
    continue
  fi

  echo "Generating diffs for ${project} ${version}"
  "${main_root}/scripts/generate_project_diff.sh" "$project" "$version"
done
