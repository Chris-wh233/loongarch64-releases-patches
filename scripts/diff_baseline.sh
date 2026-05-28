#!/usr/bin/env bash
set -euo pipefail

path="${1:?path is required}"
label="${2:-baseline}"

mkdir -p "$path"
rm -rf "$path/.git"

git -C "$path" init -q
git -C "$path" config user.name "diff-generator"
git -C "$path" config user.email "diff-generator@example.invalid"

git -C "$path" add -A
if git -C "$path" diff --cached --quiet; then
  git -C "$path" commit --allow-empty -q -m "baseline: $label"
else
  git -C "$path" commit -q -m "baseline: $label"
fi
