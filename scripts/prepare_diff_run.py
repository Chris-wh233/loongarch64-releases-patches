#!/usr/bin/env python3
import json
import shutil
import stat
import sys
from pathlib import Path


def load_project(config_path: Path, name: str) -> dict:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    for project in data["projects"]:
        if project["name"] == name:
            merged = dict(project)
            merged["architecture"] = data["architecture"]
            return merged
    raise SystemExit(f"unknown project: {name}")


def chmod_exec(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def copy_helper_scripts(repo_root: Path, main_root: Path) -> None:
    scripts_dir = repo_root / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    for name in ("diff_baseline.sh", "diff_capture.sh"):
        target = scripts_dir / name
        shutil.copy2(main_root / "scripts" / name, target)
        chmod_exec(target)


def patch_source_tag_usage(lines: list[str]) -> list[str]:
    patched = []
    for line in lines:
        line = line.replace('-b "${VERSION}"', '-b "${SOURCE_TAG}"')
        line = line.replace("-b ${VERSION}", "-b ${SOURCE_TAG}")
        line = line.replace("/archive/refs/tags/v${VERSION}.tar.gz", "/archive/refs/tags/${SOURCE_TAG}.tar.gz")
        line = line.replace("/archive/refs/tags/${VERSION}.tar.gz", "/archive/refs/tags/${SOURCE_TAG}.tar.gz")
        line = line.replace("/archive/refs/tags/v$VERSION.tar.gz", "/archive/refs/tags/${SOURCE_TAG}.tar.gz")
        line = line.replace("/archive/refs/tags/$VERSION.tar.gz", "/archive/refs/tags/${SOURCE_TAG}.tar.gz")
        patched.append(line)
    return patched


def add_source_tag_default(lines: list[str], source_tag: str) -> list[str]:
    if any("SOURCE_TAG=" in line for line in lines[:30]):
        return lines

    insertion = [f'SOURCE_TAG="${{SOURCE_TAG:-{source_tag}}}"\n']
    for idx, line in enumerate(lines):
        if line.startswith("VERSION="):
            return lines[: idx + 1] + insertion + lines[idx + 1 :]

    for idx, line in enumerate(lines[:10]):
        if line.startswith("set "):
            return lines[: idx + 1] + insertion + lines[idx + 1 :]

    return lines[:1] + insertion + lines[1:]


def diff_groups(project: dict) -> list[dict]:
    groups = []
    if all(k in project for k in ("patch_baseline", "patch_anchor", "diff_dir", "diff_file")):
        groups.append({
            "id": "default",
            "patch_baseline": project["patch_baseline"],
            "patch_anchor": project["patch_anchor"],
            "diff_dir": project["diff_dir"],
            "diff_file": project["diff_file"],
        })

    idx = 1
    while True:
        keys = {
            "patch_baseline": f"patch_baseline_{idx}",
            "patch_anchor": f"patch_anchor_{idx}",
            "diff_dir": f"diff_dir_{idx}",
            "diff_file": f"diff_file_{idx}",
        }
        present = [key in project for key in keys.values()]
        if not any(present):
            break
        if not all(present):
            missing = [name for name, key in keys.items() if key not in project]
            raise SystemExit(f"{project['name']} has incomplete diff group {idx}: missing {', '.join(missing)}")
        groups.append({
            "id": str(idx),
            "patch_baseline": project[keys["patch_baseline"]],
            "patch_anchor": project[keys["patch_anchor"]],
            "diff_dir": project[keys["diff_dir"]],
            "diff_file": project[keys["diff_file"]],
        })
        idx += 1

    return groups


def shell_files(repo_root: Path) -> list[Path]:
    files = [repo_root / "scripts" / "build.sh"]
    for directory in (repo_root / "scripts", repo_root / "patches"):
        if directory.exists():
            files.extend(sorted(path for path in directory.glob("*.sh") if path not in files))
    return [path for path in files if path.exists()]


def find_anchor(files: dict[Path, list[str]], needle: str, label: str) -> tuple[Path, int]:
    matches = []
    for path, lines in files.items():
        for idx, line in enumerate(lines):
            if needle in line:
                matches.append((path, idx))
    if not matches:
        raise SystemExit(f"cannot find {label} anchor: {needle}")
    return matches[0]


def add_insertion(insertions: dict[Path, dict[int, dict[str, list[str]]]], path: Path, idx: int, position: str, lines: list[str]) -> None:
    insertions.setdefault(path, {}).setdefault(idx, {"before": [], "after": []})[position].extend(lines)


def patch_shell_files(repo_root: Path, project: dict, version: str, source_tag: str, output_dir: str) -> None:
    groups = diff_groups(project)
    if not groups:
        raise SystemExit(f"{project['name']} has no diff groups; define patch_baseline/patch_anchor/diff_dir/diff_file")

    files = {path: path.read_text(encoding="utf-8").splitlines(keepends=True) for path in shell_files(repo_root)}
    build_sh = repo_root / "scripts" / "build.sh"
    if build_sh not in files:
        raise SystemExit(f"missing build script: {build_sh}")
    files[build_sh] = add_source_tag_default(patch_source_tag_usage(files[build_sh]), source_tag)

    insertions: dict[Path, dict[int, dict[str, list[str]]]] = {}
    build_capture_indexes = []

    for group in groups:
        baseline_path, baseline_idx = find_anchor(files, group["patch_baseline"], f"{project['name']} baseline {group['id']}")
        capture_path, capture_idx = find_anchor(files, group["patch_anchor"], f"{project['name']} capture {group['id']}")
        label = f"{project['name']}-{group['id']}-{group['diff_file']}"

        add_insertion(
            insertions,
            baseline_path,
            baseline_idx,
            "before",
            [
                "\n",
                f"# diff-generator: establish baseline for {group['diff_file']}\n",
                '_diff_root="$(cd "$(dirname "$0")/.." && pwd)"\n',
                f'bash "${{_diff_root}}/scripts/diff_baseline.sh" "{group["diff_dir"]}" "{label}"\n',
            ],
        )
        add_insertion(
            insertions,
            capture_path,
            capture_idx,
            "after",
            [
                "\n",
                f"# diff-generator: capture {group['diff_file']}\n",
                '_diff_root="$(cd "$(dirname "$0")/.." && pwd)"\n',
                f'bash "${{_diff_root}}/scripts/diff_capture.sh" "{group["diff_dir"]}" "{output_dir}" "{group["diff_file"]}" "{project["name"]}" "{version}"\n',
            ],
        )
        if capture_path == build_sh:
            build_capture_indexes.append(capture_idx)

    if not build_capture_indexes:
        raise SystemExit(f"{project['name']} has no capture anchor in scripts/build.sh; cannot stop before binary build")

    final_idx = max(build_capture_indexes)
    add_insertion(
        insertions,
        build_sh,
        final_idx,
        "after",
        [
            "\n",
            "# diff-generator: stop after configured diff captures\n",
            "exit 0\n",
        ],
    )

    for path, lines in files.items():
        path_insertions = insertions.get(path, {})
        rewritten = []
        for idx, line in enumerate(lines):
            rewritten.extend(path_insertions.get(idx, {}).get("before", []))
            rewritten.append(line)
            rewritten.extend(path_insertions.get(idx, {}).get("after", []))
        path.write_text("".join(rewritten), encoding="utf-8")
        if path.suffix == ".sh":
            chmod_exec(path)


def main() -> int:
    if len(sys.argv) != 7:
        print("usage: prepare_diff_run.py <main-root> <ci-root> <project> <version> <source-tag> <output-dir>", file=sys.stderr)
        return 2

    main_root = Path(sys.argv[1]).resolve()
    repo_root = Path(sys.argv[2]).resolve()
    project_name = sys.argv[3]
    version = sys.argv[4]
    source_tag = sys.argv[5]
    output_dir = sys.argv[6]

    project = load_project(main_root / "projects.json", project_name)
    copy_helper_scripts(repo_root, main_root)

    patch_shell_files(repo_root, project, version, source_tag, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
