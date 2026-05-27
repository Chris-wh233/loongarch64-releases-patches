#!/usr/bin/env python3
import json
import os
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


def insert_after(lines: list[str], needle: str, insertion: list[str], label: str) -> list[str]:
    for idx, line in enumerate(lines):
        if needle in line:
            return lines[: idx + 1] + insertion + lines[idx + 1 :]
    raise SystemExit(f"cannot find {label} anchor: {needle}")


def insert_before(lines: list[str], needle: str, insertion: list[str], label: str) -> list[str]:
    for idx, line in enumerate(lines):
        if needle in line:
            return lines[:idx] + insertion + lines[idx:]
    raise SystemExit(f"cannot find {label} anchor: {needle}")


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


def patch_dockerfile(repo_root: Path) -> None:
    dockerfile = repo_root / "Dockerfile.build"
    if not dockerfile.exists():
        raise SystemExit(f"Dockerfile.build not found: {dockerfile}")

    text = dockerfile.read_text(encoding="utf-8")
    marker = "# diff-generator: ensure git is available for diff capture"
    if marker in text:
        return

    install_layer = [
        "\n",
        f"{marker}\n",
        "RUN if command -v git >/dev/null 2>&1; then \\\n",
        "        exit 0; \\\n",
        "    elif command -v apt-get >/dev/null 2>&1; then \\\n",
        "        apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*; \\\n",
        "    elif command -v apk >/dev/null 2>&1; then \\\n",
        "        apk add --no-cache git ca-certificates; \\\n",
        "    elif command -v dnf >/dev/null 2>&1; then \\\n",
        "        dnf install -y git ca-certificates && dnf clean all; \\\n",
        "    elif command -v yum >/dev/null 2>&1; then \\\n",
        "        yum install -y git ca-certificates && yum clean all; \\\n",
        "    elif command -v microdnf >/dev/null 2>&1; then \\\n",
        "        microdnf install -y git ca-certificates && microdnf clean all; \\\n",
        "    else \\\n",
        "        echo 'No supported package manager found to install git' >&2; exit 1; \\\n",
        "    fi\n",
    ]

    lines = text.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        if line.lstrip().upper().startswith("FROM "):
            lines = lines[: idx + 1] + install_layer + lines[idx + 1 :]
            dockerfile.write_text("".join(lines), encoding="utf-8")
            return

    raise SystemExit(f"cannot find FROM line in {dockerfile}")


def patch_milvus_helpers(repo_root: Path) -> None:
    conan_patch = repo_root / "patches" / "conan_patch.sh"
    dep_patch = repo_root / "patches" / "dep_patch.sh"

    conan_lines = conan_patch.read_text(encoding="utf-8").splitlines(keepends=True)
    conan_lines = insert_after(
        conan_lines,
        "conan config init",
        [
            '_diff_root="$(cd "$(dirname "$0")/.." && pwd)"\n',
            'cat > "$HOME/.conan/.gitignore" <<EOF\n',
            "data/\n",
            "EOF\n",
            'bash "${_diff_root}/scripts/diff_baseline.sh" "$HOME/.conan" "milvus-conan-home"\n',
        ],
        "milvus conan config",
    )
    conan_patch.write_text("".join(conan_lines), encoding="utf-8")

    dep_lines = dep_patch.read_text(encoding="utf-8").splitlines(keepends=True)
    dep_lines = insert_after(
        dep_lines,
        "    conan_download_dep",
        [
            '    _diff_root="$(cd "$(dirname "$0")/.." && pwd)"\n',
            '    bash "${_diff_root}/scripts/diff_baseline.sh" "$HOME/.conan/data" "milvus-conan-data"\n',
        ],
        "milvus conan data",
    )
    dep_patch.write_text("".join(dep_lines), encoding="utf-8")


def patch_build(repo_root: Path, main_root: Path, project: dict, version: str, output_dir: str) -> None:
    build_sh = repo_root / "scripts" / "build.sh"
    lines = build_sh.read_text(encoding="utf-8").splitlines(keepends=True)

    source_expr = project.get("source_dir_template", "${SRCS}/${VERSION}")
    baseline_anchor = project.get("baseline_anchor") or project["patch_anchor"]
    baseline = [
        "\n",
        "# diff-generator: establish baseline before LoongArch64 adaptations\n",
        f'bash "${{ROOT_DIR}}/scripts/diff_baseline.sh" "{source_expr}" "{project["name"]}-source"\n',
    ]
    lines = insert_before(lines, baseline_anchor, baseline, "baseline")

    if project.get("special") == "next_cargo":
        lines = insert_before(
            lines,
            "sed -i",
            [
                '      bash "${ROOT_DIR}/scripts/diff_baseline.sh" "$(dirname "$(dirname "${cty}")")" "nextjs-cargo-cty"\n',
            ],
            "next.js cargo baseline",
        )

    capture = [
        "\n",
        "# diff-generator: capture diffs and stop before binary build continues\n",
        f'bash "${{ROOT_DIR}}/scripts/diff_capture.sh" "{source_expr}" "{output_dir}" "{project["name"]}" "{version}"\n',
        "exit 0\n",
    ]
    lines = insert_after(lines, project["patch_anchor"], capture, "capture")
    build_sh.write_text("".join(lines), encoding="utf-8")
    chmod_exec(build_sh)


def main() -> int:
    if len(sys.argv) != 6:
        print("usage: prepare_diff_run.py <main-root> <ci-root> <project> <version> <output-dir>", file=sys.stderr)
        return 2

    main_root = Path(sys.argv[1]).resolve()
    repo_root = Path(sys.argv[2]).resolve()
    project_name = sys.argv[3]
    version = sys.argv[4]
    output_dir = sys.argv[5]

    project = load_project(main_root / "projects.json", project_name)
    copy_helper_scripts(repo_root, main_root)
    patch_dockerfile(repo_root)

    if project.get("special") == "milvus_conan":
        patch_milvus_helpers(repo_root)
    if project_name == "next.js":
        project["special"] = "next_cargo"

    patch_build(repo_root, main_root, project, version, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
