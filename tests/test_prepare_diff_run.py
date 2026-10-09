import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_diff_run import diff_groups, load_project, patch_shell_files  # noqa: E402


class PrepareDiffRunTests(unittest.TestCase):
    def test_milvus_nested_conan_scripts_get_all_three_diff_groups(self):
        project = load_project(ROOT / "projects.json", "milvus", "3.0.2")
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            build = repo / "scripts" / "build.sh"
            conan = repo / "patches" / "conan2" / "conan_patch.sh"
            dep = repo / "patches" / "conan2" / "dep_patch.sh"
            for path in (build, conan, dep):
                path.parent.mkdir(parents=True, exist_ok=True)
            build.write_text(
                '#!/bin/bash\nVERSION="${1}"\n'
                '"${PATCHES}/milvus_patch.sh" "${SRCS}/${VERSION}" "${VERSION}"\n'
                '"${PATCHES}/${CONAN}/conan_patch.sh" "${SRCS}/${VERSION}" "${PATCHES}"\n'
                '"${PATCHES}/${CONAN}/dep_patch.sh" "${SRCS}/${VERSION}" "${PATCHES}"\n'
                'make install\n',
                encoding="utf-8",
            )
            conan.write_text('conan remote add default-conan-local2 "$URL"\n', encoding="utf-8")
            dep.write_text('dep_list_from_conan+=("b2")\n', encoding="utf-8")

            patch_shell_files(repo, project, "3.0.2", "v3.0.2", "/src/diff-output")

            build_text = build.read_text(encoding="utf-8")
            self.assertEqual(build_text.count("scripts/diff_capture.sh"), 3)
            self.assertLess(build_text.index('"thirdparty_dep.patch"'), build_text.index("exit 0"))
            for path in (conan, dep):
                text = path.read_text(encoding="utf-8")
                self.assertIn('$(dirname "${BASH_SOURCE[0]}")/../..', text)
                self.assertIn("scripts/diff_baseline.sh", text)

    def test_numbered_groups_cannot_skip_an_index(self):
        with self.assertRaisesRegex(SystemExit, "incomplete diff group 1"):
            diff_groups({"name": "sample", "diff_file_2": "later.patch"})

    def test_milvus_2_uses_conan1_directory_and_anchors(self):
        project = load_project(ROOT / "projects.json", "milvus", "2.6.21")
        self.assertEqual(project["diff_dir_2"], "$HOME/.conan")
        self.assertEqual(project["diff_dir_3"], "$HOME/.conan")
        self.assertIn("default-conan-local", project["patch_baseline_2"])

        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            build = repo / "scripts" / "build.sh"
            build.parent.mkdir(parents=True)
            build.write_text(
                '#!/bin/bash\nVERSION="${1}"\n'
                '"${PATCHES}/milvus_patch.sh" "${SRCS}/${VERSION}" "${VERSION}"\n'
                '"${PATCHES}/${CONAN}/conan_patch.sh" "${SRCS}/${VERSION}" "${PATCHES}"\n'
                '"${PATCHES}/${CONAN}/dep_patch.sh" "${SRCS}/${VERSION}" "${PATCHES}"\n',
                encoding="utf-8",
            )
            for branch in ("conan1", "conan2"):
                directory = repo / "patches" / branch
                directory.mkdir(parents=True)
                (directory / "conan_patch.sh").write_text(
                    'conan remote add default-conan-local "$CONAN_ARTIFACTORY_URL"\n'
                    if branch == "conan1" else 'conan remote add default-conan-local2 "$URL"\n',
                    encoding="utf-8",
                )
                (directory / "dep_patch.sh").write_text('    conan_patch_dep\n', encoding="utf-8")

            patch_shell_files(repo, project, "2.6.21", "v2.6.21", "/src/diff-output")

            self.assertIn("scripts/diff_baseline.sh", (repo / "patches/conan1/dep_patch.sh").read_text())
            self.assertNotIn("scripts/diff_baseline.sh", (repo / "patches/conan2/dep_patch.sh").read_text())


if __name__ == "__main__":
    unittest.main()
