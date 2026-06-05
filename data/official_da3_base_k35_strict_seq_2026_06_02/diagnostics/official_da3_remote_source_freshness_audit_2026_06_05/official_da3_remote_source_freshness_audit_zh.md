# Official DA3 remote source freshness audit

日期：2026-06-05

## 结论

- status: `pass_local_official_source_matches_remote_main`
- local official source stale: `false`
- remote main sha: `41736238f5bced4debf3f2a12375d2466874866d`
- local HEAD sha: `41736238f5bced4debf3f2a12375d2466874866d`

本地用于复刻的官方 Depth-Anything-3 源码没有落后于公开 GitHub main。当前差异不是“官方代码没更新”，而是产品侧还缺 `DA3BASE_280x504_N35_image_only.mlpackage/.mlmodelc` 及其 image-only CoreML signature。

## Evidence

- Official remote: `https://github.com/ByteDance-Seed/Depth-Anything-3`
- GitHub API main commit: `41736238f5bced4debf3f2a12375d2466874866d`
- Commit date UTC: `2026-03-21T07:14:45Z`
- Commit message: `Update README.md`
- Local official repo: `/Users/kaidongwang/Documents/progecttwo/aether_cpp/third_party/Depth-Anything-3`

