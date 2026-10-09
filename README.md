# loongarch64-releases-patches

本项目把 [loongarch64-releases](https://github.com/loongarch64-releases) 各 CI 仓库中通过 `patches/` 脚本应用的源码修改，转换成可审阅的 Git diff 格式 `.patch` 文件。转换目标、插入位置和输出路径由 [`projects.json`](projects.json) 配置。

生成器克隆目标 CI 仓库，在临时副本中修改 `scripts/build.sh` 和补丁脚本：补丁执行前对指定目录执行 `git init`、`git add` 和基线提交；补丁执行后导出 `git diff --binary`。最后一次捕获必须位于 `scripts/build.sh`，生成器会在此退出，避免进入后续的二进制编译。脚本仍可能安装工具、下载上游源码或 Conan 配方，这些是执行补丁本身所需的步骤。

## 目录与流程

| 路径 | 用途 |
| --- | --- |
| `projects.json` | 项目、CI 仓库、依赖包和一组或多组 diff 锚点 |
| `Dockerfile.base` | 最小化的 LoongArch64 容器基础镜像 |
| `scripts/generate_all_diffs.sh` | 按配置生成所有项目，或指定项目及版本 |
| `scripts/generate_project_diff.sh` | 克隆 CI 仓库、准备脚本、运行容器并检查结果 |
| `scripts/prepare_diff_run.py` | 在临时 CI 副本中插入基线与捕获调用 |
| `scripts/diff_baseline.sh`、`scripts/diff_capture.sh` | 建立 Git 基线并导出补丁 |
| `diff-patches/<项目>/<版本>/` | 生成的 `.patch` 和 `manifest.json` |
| `diff-patches/<项目>/metadata.json` | 最近一次生成的版本、来源和文件清单 |

运行时的 CI 克隆、脚本副本及临时 Dockerfile 放在被忽略的 `_work/` 下。`Dockerfile.base` 是实际使用的基础镜像；项目的 `docker_image` 字段记录上游 CI 使用的镜像，供配置参考，并不决定生成容器的 `FROM`。

## 运行

需要 Linux 环境、Python 3.9 或更新版本、Git、Docker，以及能够运行 `linux/loong64` 容器的 LoongArch64 主机或 QEMU 环境。Docker 容器必须能访问上游源码和补丁依赖。查询最新 CI Release 时还需要已登录的 GitHub CLI (`gh`)；直接指定版本时不需要 `gh`。

```bash
# 指定项目和 CI Release 版本
./scripts/generate_project_diff.sh milvus 3.0.2

# 等价的已有项目快捷脚本
./diff-patches/milvus/gen_diff.sh 3.0.2

# 查询并生成所有启用项目的最新版本
./scripts/generate_all_diffs.sh

# 查询某个项目的最新版本；指定版本时无需查询 GitHub
./scripts/generate_all_diffs.sh milvus
./scripts/generate_all_diffs.sh milvus 3.0.0
```

批量入口 `generate_all_diffs.sh` 会跳过已有 `manifest.json` 且满足 `required_diff_files` 要求的版本；缺少必需文件时会重新生成。单项目入口 `generate_project_diff.sh` 总是重新生成。缺少必需文件会报错，并保留原有产物。有些项目在特定版本可能没有非空修改，因此只有确实必须产出的文件才应加入 `required_diff_files`。对于 Milvus 3.0.0、3.0.1、3.0.2 等旧版本，需要分别指定版本重新生成，才能补齐历史目录中的 Conan 补丁。

CI 工作流 [`.github/workflows/generate-diffs.yml`](.github/workflows/generate-diffs.yml) 每天运行一次，也支持手动输入 `project`，以及与 `project` 搭配的 `version`。工作流使用 QEMU/Buildx，并在产物变化时提交 `diff-patches/`。仓库需要启用 GitHub Actions，且工作流的 `GITHUB_TOKEN` 需要 `contents: write` 权限。当前工作流将该令牌传给 `gh`，无需额外密钥。

## 通过 `projects.json` 新增转换目标

先查看目标 `loongarch64-releases/<项目>` 的 `scripts/build.sh`、`patches/` 和 Release 标签，确认补丁执行时机及修改目录。随后在 `projects` 数组中加入**唯一**的项目项。一个补丁组的最小示例：

```json
{
  "name": "example",
  "ci_repo": "loongarch64-releases/example",
  "upstream": "example-org/example",
  "patched": true,
  "docker_image": "上游 CI 的镜像名（仅作记录）",
  "diff_notes": "说明此补丁包含哪些修改",
  "extra_packages": ["unzip", "pip:some-tool==1.2.3"],
  "patch_baseline": "\"${PATCHES}/patch.sh\" \"${SRCS}/${VERSION}\"",
  "patch_anchor": "\"${PATCHES}/patch.sh\" \"${SRCS}/${VERSION}\"",
  "diff_dir": "${SRCS}/${VERSION}",
  "diff_file": "example_src.patch",
  "required_diff_files": ["example_src.patch"]
}
```

将该对象作为 `projects` 的一个元素加入，注意与相邻对象之间的逗号。各字段含义：

| 字段 | 说明 |
| --- | --- |
| `name` | 本项目使用的唯一名称，也是输出目录名 |
| `ci_repo` | 目标 CI 仓库的 `owner/repo`；用于克隆及查询最新 Release |
| `upstream` | 被打补丁的真实上游仓库；写入元数据 |
| `patched` | `true` 才执行转换；`false` 仅记录项目 |
| `docker_image` | 上游 CI 镜像的参考信息；生成器实际使用 `Dockerfile.base` |
| `extra_packages` | 容器附加依赖；普通名称由 `apt-get` 安装，`pip:` 前缀由 `pip` 安装 |
| `diff_notes` | 补丁内容说明，写入元数据 |
| `patch_baseline` | Shell 源码中一段唯一的原文；在匹配行**之前**建立 Git 基线 |
| `patch_anchor` | Shell 源码中一段唯一的原文；在匹配行**之后**导出 diff |
| `patch_baseline_file`、`patch_anchor_file` | 可选；锚点重复时，用相对 CI 仓库根目录的脚本路径限定搜索范围 |
| `diff_dir` | 建立基线与导出 diff 的同一目录，支持 Shell 变量，如 `$HOME/.conan2` |
| `diff_file` | 该组的输出文件名，通常为 `.patch` |
| `required_diff_files` | 可选；必须生成的非空补丁文件名列表，缺失时本次生成失败，旧目录会重新生成 |
| `skip_build` | 可选；`true` 时定时批量运行跳过，手动指定项目仍可运行 |

锚点按原样在 CI 副本的 `scripts/build.sh`、`scripts/**/*.sh` 和 `patches/**/*.sh` 中查找。请选能唯一定位的文本，并确保基线行先于补丁操作执行、捕获行在操作完成后执行。至少一个 `patch_anchor` 必须位于 `scripts/build.sh`，作为退出编译流程的位置；若有多个，以该文件中最后一个捕获点为准。锚点可以位于嵌套目录中的补丁脚本，例如 `patches/conan2/conan_patch.sh`。

同一项目需要多份补丁时，使用连续编号的四字段组：`patch_baseline_1`、`patch_anchor_1`、`diff_dir_1`、`diff_file_1`，再写 `_2`、`_3` 等。每组独立建立基线和导出 diff；编号不能跳过，四个字段必须齐全。Milvus 即用三组分别生成源码、Conan 配置和第三方配方补丁。未编号组也可用于单个输出。

如果 CI 脚本按主版本选择不同补丁目录，可加 `major_version_overrides`。键是版本号第一个点号前的部分，值中只写需要覆盖的字段。Milvus 以 3.x 的 `conan2` 为默认配置，并在 `"2"` 中把 Conan 目录改为 `$HOME/.conan`，同时把基线锚点限定到 `patches/conan1/`。编号组的限定字段为 `patch_baseline_file_2`、`patch_anchor_file_2` 等。版本覆盖只影响该次准备脚本的过程，不改变配置文件本身。

```json
"major_version_overrides": {
  "2": {
    "patch_baseline_3": "    conan_patch_dep",
    "patch_baseline_file_3": "patches/conan1/dep_patch.sh",
    "diff_dir_3": "$HOME/.conan"
  }
}
```

新增配置后先运行 `python3 -m json.tool projects.json >/dev/null` 检查 JSON，再运行 `./scripts/generate_project_diff.sh <name> <版本>`。检查目标版本的 `manifest.json` 和每个 `.patch` 是否齐全，必要时用 `git apply --check <文件>` 在对应原始目录验证。可以选择添加 `diff-patches/<name>/gen_diff.sh` 快捷脚本；生成器和 CI 不要求它存在。

如果上游工作流包含 `LATEST_VERSION=${LATEST_VERSION#v}`，生成器将 CI Release 的无 `v` 版本号用于补丁脚本，并为源码检出使用 `v<版本>` 标签。否则按传入的版本号检出源码。
