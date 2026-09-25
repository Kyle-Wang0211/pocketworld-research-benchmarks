# LOD 会话归档(2026-09-25,清盘前)

接在 `data/lod-session-archive-20260924`(bd5bb82)之后。那份快照是 09-24 18:08 拍的;本份补上之后
171→174 出包、装机前核对留下的结果,以及 splat 台架的源码。推送后才删本机的可重建产物(清单见
`MANIFEST.tsv` 里 `archived_path = -` 的行,每行写了来源和重建路线)。

路径前缀同上一份:`<SP>` = 会话 scratchpad(重启即清),`<BENCH>` = `~/Developer/pw_splat_ab_bench/`
(本机 git 仓,无远端)。

## 内容

- `lod171_after_0924_snapshot/`(39 个文件):上一份快照之后新增或改过的结果 —— 171–174 四个包的逐文件
  sha256 清单、`check168/171/172/172_on171/173/174.txt`(装机前核对输出)、`analyze_*.txt`、
  `assemble17x.log`、`build_17x.log`、`cmp_168_vs_171.txt`、`test_*_results.json` 与 `.rc`(各候选的
  `flutter test` 汇总;原始事件流 `.jsonl` 未收,可在对应提交上重跑)。
- `mac_lod_bench_src/`:`<BENCH>` 在 `b792d57` 的被跟踪源码(Sources、mac、xcodeproj、project.yml、
  分析脚本、跑测脚本、`ply2bin.cpp`、自带的 `aether_pointcloud_lod` 与其中 nlohmann/json(MIT,带
  LICENSE))。报告、计划与结果文本在上一份的 `mac_lod_bench/tracked/`。只收文件、不收历史:历史里带设备号
  与邮箱,上一份已因此撤下 bundle。
- `review_cache_sha_map.txt`:产品仓 169/170 本地提交 → 已推 `snapshot/review-cache-169-170` 的对应
  (只把作者/提交者邮箱换成 GitHub noreply,树、说明、时间不变)。
- `Runner-169.sha256manifest.txt`:删包前算的 169 包逐文件 sha256。

## 打码

`MANIFEST.tsv` 里标 REDACTED 的 12 个文件:本机家目录路径 → `~`,手机设备号 → `<device-coredevice-id>`,
签名身份里的邮箱 → `<user-email>`,团队号 → `<team-id>`。其余出现的 UUID 是 Mach-O 二进制的 LC_UUID;
`17.0.0.170` 是版本串;几处邮箱是第三方许可证原文。

## 相关分支(推送时远端 head)

| 仓 | 分支 | head |
|---|---|---|
| pocketworld | `feat/lod-on-dense-168` | `c6203de`(171 = `04d7353`,172 = `5ca138c`,174 = `de0dad1`,生产现为 174) |
| pocketworld | `snapshot/review-cache-169-170` | `08a1bd7`(169 = `4a2c18d`,170 = `08a1bd7`) |
| pocketworld | `snapshot/prod-168` | `86a45cf` |
| Aether3D | `feat/pointcloud-lod-viewer` | `72ee817` |

## 没收的

- 手机日志 `devlog171/`、`post172/`(含 jetsam 报告里的全机进程表、容器清单):不公开,移到本机
  `~/Developer/pw_lod_data/device_logs_171_172/` 留存。
- 给子 agent 的消息草稿、台账旧副本(台账本体 `~/Developer/pw_builds_20260904/README.md` 仍在本机)。
