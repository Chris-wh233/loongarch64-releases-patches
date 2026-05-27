#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path


def project_packages(project: dict) -> list[str]:
    return list(project.get("extra_packages", []))


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: render_diff_dockerfile.py <main-root> <project|__all__> <output-dockerfile> <image-name-file>", file=sys.stderr)
        return 2

    main_root = Path(sys.argv[1]).resolve()
    selector = sys.argv[2]
    output = Path(sys.argv[3]).resolve()
    image_name_file = Path(sys.argv[4]).resolve()

    config = json.loads((main_root / "projects.json").read_text(encoding="utf-8"))
    projects = [p for p in config["projects"] if p.get("patched")]
    if selector == "__all__":
        projects = [p for p in projects if not p.get("skip_build", False)]
    else:
        projects = [p for p in projects if p["name"] == selector]
        if not projects:
            raise SystemExit(f"unknown patched project: {selector}")

    packages: list[str] = []
    for project in projects:
        packages.extend(project_packages(project))

    apt_packages = sorted({p for p in packages if not p.startswith("pip:")})
    pip_packages = sorted({p[4:] for p in packages if p.startswith("pip:")})

    base = (main_root / "Dockerfile.base").read_text(encoding="utf-8").rstrip() + "\n"
    trailing_cmd = ""
    if apt_packages or pip_packages:
        base_lines = base.splitlines(keepends=True)
        for idx in range(len(base_lines) - 1, -1, -1):
            if not base_lines[idx].strip():
                continue
            if base_lines[idx].lstrip().startswith("CMD "):
                trailing_cmd = base_lines.pop(idx)
                base = "".join(base_lines).rstrip() + "\n"
            break
    chunks = [base]
    if apt_packages:
        package_lines = " \\\n      ".join(apt_packages)
        chunks.append(
            "\nRUN apt-get update && \\\n"
            "    apt-get install -y --no-install-recommends \\\n"
            f"      {package_lines} && \\\n"
            "    rm -rf /var/lib/apt/lists/*\n"
        )

    if pip_packages:
        pip_lines = " ".join(f"'{pkg}'" for pkg in pip_packages)
        chunks.append(f"\nRUN python3 -m pip install --break-system-packages {pip_lines}\n")

    if trailing_cmd:
        chunks.append("\n" + trailing_cmd)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(chunks), encoding="utf-8")

    image_suffix = selector if selector != "__all__" else "all"
    image_name = os.environ.get("DIFF_DOCKER_IMAGE", f"loongarch64-patch-diff-env-{image_suffix}")
    image_name_file.write_text(image_name + "\n", encoding="utf-8")

    print(f"Rendered {output}")
    print(f"Image: {image_name}")
    print("APT packages: " + (" ".join(apt_packages) if apt_packages else "(none)"))
    print("pip packages: " + (" ".join(pip_packages) if pip_packages else "(none)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
