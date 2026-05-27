#!/usr/bin/env bash
set -euo pipefail

project="${1:?project is required}"
version="${2:?version is required}"

main_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ci_cache="${CI_REPO_CACHE:-${main_root}/_work/ci-repos}"
run_root="${DIFF_RUN_ROOT:-${main_root}/_work/runs}"

project_json="$(python3 - "$main_root/projects.json" "$project" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
for item in data["projects"]:
    if item["name"] == sys.argv[2]:
        print(json.dumps(item))
        break
else:
    raise SystemExit(f"unknown project: {sys.argv[2]}")
PY
)"

patched="$(python3 - <<'PY' "$project_json"
import json, sys
print(str(json.loads(sys.argv[1]).get("patched", False)).lower())
PY
)"
if [ "$patched" != "true" ]; then
  echo "Project ${project} has no patches/ directory in its CI repository; skipping."
  exit 0
fi

ci_repo="$(python3 - <<'PY' "$project_json"
import json, sys
print(json.loads(sys.argv[1])["ci_repo"])
PY
)"

mkdir -p "$ci_cache" "$run_root" "${main_root}/diff-patches/${project}"
cache_dir="${ci_cache}/${project}"

if [ -d "${cache_dir}/.git" ]; then
  git -C "$cache_dir" fetch --depth 1 origin main
  git -C "$cache_dir" checkout -q FETCH_HEAD
else
  git clone --depth 1 "https://github.com/${ci_repo}.git" "$cache_dir"
fi

run_dir="${run_root}/${project}-${version}"
rm -rf "$run_dir"
mkdir -p "$run_dir"
cp -a "${cache_dir}/." "$run_dir/"

output_dir="${main_root}/diff-patches/${project}/${version}"
rm -rf "$output_dir"
mkdir -p "$output_dir"

python3 "${main_root}/scripts/prepare_diff_run.py" "$main_root" "$run_dir" "$project" "$version" "$output_dir"

chmod +x "${run_dir}/scripts/build_in_docker.sh"
"${run_dir}/scripts/build_in_docker.sh" "$version"

python3 "${main_root}/scripts/update_metadata.py" "$main_root" "$run_dir" "$project" "$version" "$output_dir"

