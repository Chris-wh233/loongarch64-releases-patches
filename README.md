# loongarch64-releases-patches

This repository generates reviewable diff files from the shell-based adaptation
patches used by `loongarch64-releases/*` CI repositories.

The original CI repositories keep LoongArch64 adaptations as shell scripts under
`patches/`. The scripts here run the same CI container path, stop immediately
after the last adaptation action, and export the resulting source changes as
diff files under `diff-patches/<project>/<version>/`.

During diff generation the temporary CI copy of `Dockerfile.build` is patched to
install `git` when the upstream build image does not already provide it. This is
required because baseline commits and diff capture run inside the LoongArch64
container.

## Layout

- `projects.json` records the CI repository, real upstream, architecture, Docker
  image source and patch anchor for each project.
- `diff-patches/<project>/gen_diff.sh` generates diffs for one project.
- `diff-patches/<project>/metadata.json` describes generated diffs and is
  updated by each generation run.
- `scripts/` contains the shared implementation used locally and by CI.
- `.github/workflows/generate-diffs.yml` runs on schedule or manually.

## Local usage

```bash
./diff-patches/milvus/gen_diff.sh 2.5.0
```

By default CI repositories are cloned under `_work/ci-repos` and temporary build
state is kept under `_work/runs`.

## GitHub repository setup

1. Enable GitHub Actions for the repository.
2. Keep the default `GITHUB_TOKEN` workflow permission, or set
   `Settings -> Actions -> General -> Workflow permissions` to
   `Read and write permissions`.
3. The workflow uses GitHub-hosted `ubuntu-latest`, Docker, QEMU and Buildx.
4. No custom secret is required unless GitHub API rate limits become a problem.
   In that case add a fine-grained token as `GH_TOKEN`; the workflow already
   passes `GITHUB_TOKEN` to `gh` by default.

The workflow commits generated diff updates back to the repository when files
change.
