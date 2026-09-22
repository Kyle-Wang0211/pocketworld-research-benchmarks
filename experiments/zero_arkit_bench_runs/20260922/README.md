# 零 ARKit 臂台架端到端 —— 2026-09-22 两跑

台架 `com.kyle.arloopbench`(`--dart-define=PW_ZERO_ARKIT_CAPTURE=true`),真源 pocketworld `feat/ios-zero-arkit-integration`;生产包一个字节不碰。

| 跑 | 引擎臂 | 喂料 | 跟踪 | 快门 | 结论 |
|---|---|---|---|---|---|
| run1 22:06(`2662850` 树) | generic | 640×480(违反「最低 1920」,已改) | 5 s 进 normal,86 s 全 normal | 13/13 超时 `unsupported` | 原生每张都写好(4032×3024 JPEG + sidecar),Dart 拿受理码 0 比 requestId 的 bug(`78bdc7c` 已修) |
| run2 22:41(`78bdc7c` 树) | gpufenothread | 1920×1440 | 3.4 s 进 normal,3.7 min 全 normal | 0(用户看预览糊,没拍) | 用户定:先做自适应对焦(镜头锁 0.835) |

`run1_220625/native_sidecars/`:13 张原生 sidecar(内参按 ×2.1 从 1920 视频连接缩放;**锁焦下 fx 仍从 2791.5 漂到 2797.1**,0.2%/13 张,与 Won & Jeon 2022 的 VCM 温漂一致)。
`bench_app_glue/`:台架非镜像部分(main.dart / 同步脚本 / Podfile / Info.plist)的快照,台架本身不是 git 仓。
