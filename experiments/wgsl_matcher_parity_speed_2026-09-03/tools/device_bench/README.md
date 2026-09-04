# PWMatchBench —— 设备侧匹配器台架(2026-09-04)

## 为什么有它
整场 WGSL 匹配器战役都在 M3 Pro 上定价(收盘 0.986x 追平原生 Metal),第一次上真机
才发现 A16 上慢 8.5x —— 而根因是设备**根本没在跑 MMA 核**。用户的话:
「你能在电脑上一遍一遍测,为什么不装个 bench app 在手机上测?我不可能一天拍几十遍
配合你,而且每次拍摄的内容移动速度和拍摄位置不可能完全一样。」

## 口径
两个后端**同一进程内交替**(不是两次启动、不靠 env),与 Mac 台架完全一致。
匹配器入口不在 xcframework 的 35 个导出面上,所以这里**直接编译同一批 TU**:
`pwofficial_gpu_match.mm`(-include 改名头 ⇒ `pwmetal_*`)/ `_dispatch.cc` /
`_dawn.cc`(-DPWOFFICIAL_DAWN_OBSERVABLES_EXTERN=1)/ `_thermal_apple.mm`,
force_load 钉定的 iOS `libwebgpu_dawn.a`。

## 用法
```
xcodegen generate && xcodebuild -project PWMatchBench.xcodeproj -scheme PWMatchBench \
  -configuration Release -destination 'generic/platform=iOS' -derivedDataPath <dd> \
  -allowProvisioningUpdates build
xcrun devicectl device install app --device <id> <dd>/Build/Products/Release-iphoneos/PWMatchBench.app
xcrun devicectl device process launch --device <id> com.kyle.PWMatchBench            # 建目录
xcrun devicectl device copy to --device <id> --domain-type appDataContainer \
  --domain-identifier com.kyle.PWMatchBench --source <fx13> --destination Documents/fixtures/fx13
xcrun devicectl device process launch --device <id> --terminate-existing \
  com.kyle.PWMatchBench -- -PWRows 13312 -PWReps 15
xcrun devicectl device copy from --device <id> --domain-type appDataContainer \
  --domain-identifier com.kyle.PWMatchBench --source Documents/MatchBench --destination <local>
```
夹具是 13312x128 的原始 u8;`-PWRows N` 取前 N 行 ⇒ **一份夹具跑任意规模**。

## 首批结果(A16,修完 subgroup 闸之后)
| rows | metal wall_p50 | dawn wall_p50 | dawn/metal | 输出 |
|---|---|---|---|---|
| 8192  | 25.832 ms | 26.483 ms | 1.025x | sha `fcb72732ae09` 逐字节相同 |
| 13312 | 70.213 ms | 70.806 ms | 1.008x | sha `a59db73512ce` 逐字节相同 |
| 13312(15 轮复跑) | 70.702 ms | 69.960 ms | **0.990x** | 逐字节相同 |

两个 sha 与 Mac 同尺寸完全一致。

🔴 已知小瑕疵:`backend_info` 原样含引号,写进 JSON 会让它不合法(下次改成转义)。
