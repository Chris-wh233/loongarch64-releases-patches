#!/usr/bin/env bash
set -euo pipefail

main_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
only_project="${1:-}"

projects="$(python3 - "$main_root/projects.json" "$only_project" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
only = sys.argv[2]
for item in data["projects"]:
    if item.get("patched") and (not only or item["name"] == only):
        print(item["name"])
PY
)"

for project in $projects; do
  tag="$(gh api "repos/loongarch64-releases/${project}/releases/latest" --jq '.tag_name')"
  version_arg="$(python3 - <<'PY' "$main_root/projects.json" "$project"
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
project = next(p for p in data["projects"] if p["name"] == sys.argv[2])
print(project.get("version_arg", "as_tag"))
PY
)"
  version="$tag"
  if [ "$version_arg" = "strip_v" ]; then
    version="${version#v}"
  fi

  if [ -f "${main_root}/diff-patches/${project}/${version}/manifest.json" ]; then
    echo "${project} ${version} already generated; skipping."
    continue
  fi

  echo "Generating diffs for ${project} ${version}"
  "${main_root}/scripts/generate_project_diff.sh" "$project" "$version"
done

