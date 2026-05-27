#!/usr/bin/env python3
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def first_from(dockerfile: Path) -> str | None:
    if not dockerfile.exists():
        return None
    for line in dockerfile.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("FROM "):
            return line.split(None, 1)[1]
    return None


def main() -> int:
    if len(sys.argv) != 7:
        print("usage: update_metadata.py <main-root> <ci-root> <project> <version> <source-tag> <diff-dir>", file=sys.stderr)
        return 2

    main_root = Path(sys.argv[1]).resolve()
    ci_root = Path(sys.argv[2]).resolve()
    project_name = sys.argv[3]
    version = sys.argv[4]
    source_tag = sys.argv[5]
    diff_dir = Path(sys.argv[6]).resolve()

    data = json.loads((main_root / "projects.json").read_text(encoding="utf-8"))
    project = next(p for p in data["projects"] if p["name"] == project_name)

    metadata_path = main_root / "diff-patches" / project_name / "metadata.json"
    previous = {}
    if metadata_path.exists():
        previous = json.loads(metadata_path.read_text(encoding="utf-8"))

    manifest_path = diff_dir / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    docker_image = first_from(main_root / "Dockerfile.diff") or project.get("docker_image")
    diff_files = sorted(p.name for p in diff_dir.glob("*.diff"))

    output = {
        "project": project_name,
        "ci_repository": project["ci_repo"],
        "upstream_repository": project["upstream"],
        "architecture": data["architecture"],
        "latest_generated_version": version,
        "upstream_source_tag": source_tag,
        "docker_image": docker_image,
        "dockerfile": "Dockerfile.diff",
        "last_generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "diff_directory": f"diff-patches/{project_name}/{version}",
        "diff_files": diff_files,
        "description": previous.get("description") or project.get("diff_notes", ""),
        "generated_manifest": manifest,
    }
    metadata_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
