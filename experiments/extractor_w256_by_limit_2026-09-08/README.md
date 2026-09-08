# 提取器布局按 `maxStorageBufferBindingSize` 自选(2026-09-08,用户批准)

## 一句话
金字塔打包缓冲的**绑定布局**不再写死,改成按设备**运行时自报的** `maxStorageBufferBindingSize`
选:绑得下整块就走旧的整缓冲布局(快),绑不下才切子区间布局(W256)。
Adreno 660 上因此白拿 **5.62×**(8823 → 1569.7 ms),一个 env 都不用设。

## 为什么这不算"单系统提速"
用户的铁律是**不做任何单系统提速**(`feedback_no_platform_specific_knives_all_platforms_together`)。
这一刀不违反,因为分叉的判据是**设备自己上报的能力数字**,不是机型名/厂商名:

| 设备 | GPU / 后端 | granted `maxStorageBufferBindingSize` | 12MP 需要 | 自动选 |
|---|---|---|---|---|
| M3 Mac | Metal | 1024 MB | 372 MB | 整缓冲(快) |
| P50 Pocket | Adreno 660 / Vulkan | **512 MB** | 372 MB | 整缓冲(快) |
| Mate 10 | Mali-G72 / Vulkan | **256 MB** | 372 MB | 子区间(唯一能跑的) |
| A16 iPhone | Metal | 未测 | 372 MB | 待测 |

同一棵树对别的 limit 本来就是这么处理的(`dawn_kernel_harness.cpp` 请求上限再按 adapter 截断)。
**任一端都不赔**:能力够的端拿回旧的快布局,能力不够的端保持唯一能跑的布局。

## 实现(`aether_cpp/tools/sift_pyramid_dawn.{h,cc}`)
- `build()` 里,在 `level_layout()` 之前,用**单区(w256=0)递推**算出所需字节 —— 那正是旧布局下
  关键点阶段要一次绑上去的那一块,所以它**就是判据本身,不是近似**;不构成循环依赖。
- 查 `harness.device().GetLimits()`(要**device** 的 granted 值,不是 adapter 的原始值)。
- `w256_enabled()`:`OFFICIAL_AETHER_W256` 两个方向都强制(台架 A/B + 生产回滚);未设时
  `required > limit`。**查不到 limit 一律选子区间** —— 猜错方向的代价不对称:
  选错成整缓冲在 Mali 上是**跑不起来**,选错成子区间只是慢。

## 自证(不走 stderr)
`SiftPyramidDawn::w256_last_decision(req, lim, enabled, forced_by_env)`,
Mac CLI 与 Android 探针都把它印在**和四摘要同一行**的 `EXTRACT` 里:
`w256=0 w256_env=0 w256_req_mb=372 w256_lim_mb=512`。
09-07 的教训:只走 stderr 的生效自证在设备上必然丢。

## 闸与数据
### Mac(Dawn/Metal,frame1.gray 4032×3024,cap 65536)三臂逐位同
| 臂 | count | desc | xy | scale | ori | w256 |
|---|---|---|---|---|---|---|
| AUTO(无 env) | 42418 | 42414d7f962d | 50b36266d43b | a68466fbdf06 | 3fa4cb355534 | 0 (req 372 / lim 1024) |
| 强制 W256=0 | 42418 | 同上 | 同上 | 同上 | 同上 | 0 |
| 强制 W256=1 | 42418 | 同上 | 同上 | 同上 | 同上 | 1 |

与 09-07 W256 落地前的基线四摘要也完全相同 ⇒ **逐字节无损**。

### P50 Pocket / Adreno 660(13312 产线口径,reps=3,BUILD_ID 9d925268e878)
| 臂 | p50 | min | 自证 |
|---|---|---|---|
| AUTO(无 env) | **1569.7** | 1540.1 | `w256=0 w256_env=0 req=372 lim=512` |
| 强制 W256=1(阳性对照) | 8823.0 | 8813.4 | `w256=1 w256_env=1` |

阳性对照的意义:证明这个判定**不是空转** —— 同一个二进制,把 env 打开就慢回去 5.62×。
每臂 `am force-stop` + 45 s 冷却(P50 连跑第 3 次必挂:`readback_short_or_timeout`,MemFree ~330 MB)。

## 未完
- 🔴 **Mate 10(Mali-G72)未验**:必须看到它自动选 `w256=1` 且 12MP 仍跑得起来。09-08 晚设备不在线
  (192.168.1.11 无响应)。**这是本刀唯一还没闭合的一端。**
- 🔴 **A16 从未测过 W256**。若生产 iOS 里 W256 是默认开的,那 A16 一直在白付这笔;
  这一刀会让它自动回到快布局 —— 但要**先量**再说,不能假设 Adreno 的 5.7× 会在 A16 复现。
- `DESC_ATOMIC` 在 Adreno 仍未测(探针 FAIL `reason=removeChild`)。

---

# 续:5.62× 到底是谁的钱(09-08 深夜)

## 段账(P50 / Adreno 660,13312,reps=3,同一个二进制)
w256=1 减 w256=0,单位 ms:

| 段 | w256=0 | w256=1 | Δ |
|---|---|---|---|
| **clamp** | 8.9 | 3241.9 | **+3233.0** |
| affine | 271.9 | 1897.8 | +1625.9 |
| orient | 196.8 | 1331.3 | +1134.5 |
| descriptor | 375.9 | 1199.8 | +823.9 |
| detect | 235.1 | 640.7 | +405.6 |
| suppress | 3.8 | 14.2 | +10.4 |
| desc_rb | 11.1 | 20.2 | +9.1 |
| **pyramid** | 462.4 | 427.8 | **−34.6** |
| 合计 | 1566 | 8774 | +7208 |

`clamp` 是回读同步点,吃的是前面排队的 GPU 活,不能单独解读。
**关键读法:钱不在"每次 dispatch 只绑触碰的层"** —— 金字塔那套碎绑定反而快了 34 ms。
6.8/7.2 s 压在关键点那一半,而那一半与 w256=0 的唯一差别是:packed 绑成 `[0, A区末尾)`,
**起点同样是 0,只是 size 从 372 MB 缩到 195 MB**。

L1B1 复现 8791.7(首测 8813.1),段形状一致 ⇒ 这批数据自洽。

## 想拆「布局」vs「绑定」,两个离对角都塌了
把 W256 拆成 `w256_enabled()`(布局)与 `w256_bind_enabled()`(绑定)两个变量后:

| 臂 | 布局 | 绑定 | 结果 |
|---|---|---|---|
| L0B0 | 单区 | 整缓冲 | 1556.8 ms ✅ |
| L1B1 | A/B | 子区间 | 8791.7 ms ✅ |
| L1B0 | A/B | 整缓冲 | 🔴 **GPU 卡死** 523 s 无进展(D 态;只印出 limits;logcat 无 Dawn/Vulkan 报错) |
| L0B1 | 单区 | 子区间 | 🔴 结构不可能:`rc=2 w256_keypoint_region_exceeds_256mb` |

L0B1 塌得有信息:单区布局下 A 区就是整块 372 MB,撞上代码里**写死的 `kWindowElems = 2^26`(256 MB)**
—— 那是 Mali 的数字被硬编码成了判据,Adreno 明明 granted 512 MB。**已改成按 granted limit 走**
(`SiftPyramidDawn::window_elems()`),Mac 逐字节复验通过。

## 🔴 一个作废的结果(必须记着,别被自己骗)
「W256=1 但只把关键点那一次绑定退回整缓冲」(KPBIND=0)量到 **8840.4**、段形状不变。
看上去像"关键点绑定无辜",**但当时探针没印 `kpbind`,阳性对照没跑成设备就被取走了** ⇒
分不清「关键点绑定无辜」和「旋钮静默没生效」。**此数作废,不得引用。**

已修:`note_kp_bind()` 记在真正建绑定那一刻,Mac/Android 探针的 `EXTRACT` 行都加了 `kpbind=`。
**Mac 上旋钮的阳性对照已通过**——`W256=1 KPBIND=0` → `w256bind=1 kpbind=0`,
`W256=0 KPBIND=1` → `w256bind=0 kpbind=1`,两个方向都独立翻转。
(Mac 本身分辨不了快慢:Metal 上 W256 只 +2.6%,156.9 vs 152.9。)

## Mac 五臂逐字节闸(含新窗口与新旋钮)
AUTO / W256=0 / W256=1 / W256=1+KPBIND=0 / W256=0+KPBIND=1 —— 五臂
`count=42418`、`42414d7f962d / 50b36266d43b / a68466fbdf06 / 3fa4cb355534` **完全相同**,
且等于 W256 落地前基线。窗口改成按 granted limit(Mac 1 GB ⇒ 检测不再拆)后摘要仍不变。

## 下次上机第一件事
1. **Mate 10(Mali)**:自动选 `w256=1` 且 12MP 跑得起来 —— 唯一没验的一端。
2. **P50 重跑 KPBIND 臂**,这次看 `kpbind=` 自报;拿不到自报就当没测。
3. `L1B0` 卡死的复现与定因(A/B 布局 + 整缓冲绑定为什么挂 GPU)。
4. `DESC_ATOMIC=0` 在 Adreno 单独查 —— 每臂都冷却过,**不是"连跑第三次"那个已知毛病**。
