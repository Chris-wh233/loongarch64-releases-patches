#!/usr/bin/env bash
set -euo pipefail
version="${1:?version is required}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
"${root}/scripts/generate_project_diff.sh" "emqx" "$version"
