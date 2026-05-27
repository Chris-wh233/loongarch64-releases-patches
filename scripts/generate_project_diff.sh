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
container_output_dir="/src/diff-output"

source_tag="$version"
if grep -R -F 'LATEST_VERSION=${LATEST_VERSION#v}' "${run_dir}/.github/workflows" >/dev/null 2>&1; then
  case "$source_tag" in
    v*) ;;
    *) source_tag="v${source_tag}" ;;
  esac
fi

echo "CI release version: ${version}"
echo "Upstream source tag: ${source_tag}"

python3 "${main_root}/scripts/prepare_diff_run.py" "$main_root" "$run_dir" "$project" "$version" "$source_tag" "$container_output_dir"

dockerfile_dir="${main_root}/_work/dockerfiles"
dockerfile_selector="${DIFF_PACKAGE_SELECTOR:-$project}"
generated_dockerfile="${dockerfile_dir}/Dockerfile.${dockerfile_selector}"
image_name_file="${dockerfile_dir}/image.${dockerfile_selector}.txt"
python3 "${main_root}/scripts/render_diff_dockerfile.py" "$main_root" "$dockerfile_selector" "$generated_dockerfile" "$image_name_file"
image_name="$(cat "$image_name_file")"
docker build -t "$image_name" -f "$generated_dockerfile" "${main_root}"

mapfile -t extra_args < <(python3 - <<'PY' "$project_json" "$version"
import json
import sys

project = json.loads(sys.argv[1])
version = sys.argv[2]

if project.get("extra_args_strategy") == "emqx_el_version":
    clear = version.lstrip("ve")
    parts = clear.split(".")
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) > 1 else 0
    ver_num = major * 1000 + minor
    if ver_num >= 5009:
        print("27")
    elif ver_num >= 5004:
        print("26")
    elif ver_num >= 5000:
        print("25")
    else:
        print("24")
else:
    for arg in project.get("extra_args", []):
        print(arg)
PY
)

docker run --rm \
  --platform linux/loong64 \
  -v "${run_dir}:/src:z" \
  -w /src \
  -e VERSION="${version}" \
  -e SOURCE_TAG="${source_tag}" \
  -e HOST_UID="$(id -u)" \
  -e HOST_GID="$(id -g)" \
  "$image_name" \
  /bin/bash -lc './scripts/build.sh "$@"' _ "$version" "${extra_args[@]}"

if [ -d "${run_dir}/diff-output" ]; then
  cp -a "${run_dir}/diff-output/." "$output_dir/"
fi

python3 "${main_root}/scripts/update_metadata.py" "$main_root" "$run_dir" "$project" "$version" "$source_tag" "$output_dir"
