# U3 #4 — Merrell 净票硬否决原型(cap50)

诚实结论(一句话):**Merrell 净票(stability = support − 反对)如设计般治好了"一票定罪"对弱纹理真点的误杀,但结构性地杀不掉 plane-sweep 椅子压扁假阳——因为上游没有能对抗强 support 的每视反证证据。** 这坐实了 #5 的收敛判断:根在上游,不在下游投票规则。

- 🟢 有实测:PLY + viewer + 门拒统计,确定性两跑字节一致,峰值 RSS 0.09 GB。
- 铁律遵守:只落研究 worktree 本目录;未碰生产代码、未 reset/clean、未动他人 dirty、未 git commit(留编排者统一提交);未产候选自批准——只出脚本/数字/viewer/manifest+SHA-256。
- 未读任何 4K 像素:support 从冻结 union PLY 读出(逐字节校验 SHA),opposition 只需 18 MB L1 深度图 + 位姿。

---

## 1. 机制(Merrell ICCV 2007,论文可证,忠实改编)

对候选 3D 点 P 与一组**独立每视深度图** D_k:

- **support**:独立视图光度/几何一致地认为表面在 P 处。
- **free-space 违规(反对)**:D_k 在同一条视线上测到比 P **更远**的表面(z_P < d_k − τ)。D_k 观测到那段空间是空的,P 占据它 → 一张有符号"反对"票。
- **occlusion(不算违规)**:D_k 测到比 P **更近**的表面(z_P > d_k + τ)。P 只是被更近的表面挡住,物理上一致(可能是被遮的更远表面)。Merrell **明确不因 occlusion 定罪**。
- **abstain**:P 投影出界,或该处 D_k 置信度低。

`stability(P) = support(P) − freespace_violations(P)`。Merrell 规则:`stability ≥ 0` 存活(支持数不少于 free-space 反对数);**单次 free-space 违规在被 support 压过时不判死**。

## 2. cap50 上实际可用的证据源(零捏造)

- **support(plane-sweep 候选)** = 冻结进 pinned union PLY 的光度 ZNCC clique 大小 `nviews`(≥3 视一致认为地板表面在该格)。本原型**不重算**,直接读并断言 union PLY 复刻冻结字节 SHA(`fdf5b105…`,13,488 点)。
- **opposition** = 对本 capture 上**唯一存在**的独立每视深度图—— 5 张设备端 L1(CasDiffMVS)深度图 `l1_depth_{2,20,83,128,129}.bin`(正是设备鬼层仲裁用的那 5 个 ref,见 `ghost_arbitration.json` refs_used_ids)——做 free-space 违规检验。

> #5 的核心正是:plane-sweep 自身不产每视深度,所以它的候选只有 support、没有自产反证。这里我们把 capture 上**物理存在的最强反证**(5 张 L1 深度图)喂给它,诚实测量它够不够定罪椅子。

L1 深度头 `b'L1DP'|ver|frame_id|H=512|W=896`,双通道 `[depth, confidence]`;投影用 K@(3840×2160),按 `896/3840, 512/2160` 缩放采样。校准:plane-sweep 地板点投进 L1 的深度残差中位数 ±3–13 cm,证明坐标系/相机约定/缩放正确(见 `probe_depth_calib` 在 scratchpad,数字入 stats)。τ_free 主取 **10 cm**(比几厘米的地板一致残差大,噪声本身造不出反对),另扫 5 / 20 cm。

## 3. 结果(τ_free=10cm,conf>0.5)— 🟢 实测

### 全量 plane-sweep 候选(13,488)
| 门 | 判死数 | 占比 |
|---|---|---|
| **一票定罪**(free-space≥1 即杀) | **1,884** | 14.0% |
| **Merrell 净票**(stability<0 才杀) | **0** | 0.0% |

votes:free-space 反对 2,177 张、occlusion 11,898 张(≈5.5×)、depth-agreement 14,769 张。support 中位 4、min 3、max 15;任一点 free-space 反对最多 2 张 → **support 恒 ≥ 反对 → 净票判死恒为 0**。

### ② 净票门 vs 一票定罪门 —— 治误杀(Demonstration A)🟢
定义"弱纹理真地板点"= ROI 外、光度 support `nviews≥5`、却吃到 ≥1 张 L1 free-space 违规(L1 深度在弱纹理地板本就噪)。

- 一票定罪判死 **364** 个这样的真地板点;
- Merrell 净票**全数救活 364/364(100%)**:救活点 support 中位 **5** vs 反对中位 **1** → 净票 4 ≥ 0 存活。
- τ 敏感性:τ=5cm 救活 946、τ=10cm 救活 364、τ=20cm 救活 97(单调、合理)。

**→ 净票如设计般治好了一票定罪对真点的误杀。**(viewer 面板 C 红点=一票定罪误杀区;面板 D 绿点=净票救回的真地板。)

### ③ 椅子压扁 ROI —— 诚实关键测(Demonstration B)🔴
ROI `X∈[0.25,1.05], Z∈[−1.70,−0.55]`:全部 2,466 点;其中蓝灰"椅子涂抹"非木质 515 点。

| 指标 | 值 |
|---|---|
| 净票判死 椅子涂抹 | **0 / 515(0.0%)** |
| 净票判死 整 ROI | **0 / 2,466(0.0%)** |
| 一票定罪判死 椅子涂抹 | 236 / 515 |
| ROI 内 free-space 反对票总 | 459 |
| ROI 内 occlusion 票总 | 968(≈2.1× free-space) |
| ROI 内有 L1 观测的候选 | 2,343 / 2,466 |

**净票杀不掉椅子,机制诚实归因:**
1. 椅子涂抹点携带强光度 support(中位 4,min 3);
2. 唯一反证源(5 张 L1)对每个椅子点最多给 **1** 张 free-space 反对;绝大多数要么把压扁点看成 **occlusion**(藏在真椅子后,物理一致,Merrell 拒绝据此定罪),要么在覆盖边缘 abstain。
3. 要净票判死需反对 > support,即 ≥4 张 free-space 票;但只有 5 张 L1、多数是 occlusion/abstain,ROI 内单点 free-space 反对上限=1 → **结构性不可能**。

**→ 下游净票也治不了 plane-sweep 假阳,根在上游没反证证据:plane-sweep 不产独立每视深度,没有足够密的每候选反证去对抗强 support。修复必须在上游(离面深度竞争 / 多高度假设竞争),不是加一层下游投票。**

### plane-sweep + SfM 覆盖
SfM 稀疏 92,849 点也跑了同一 opposition pass(26.7% 吃到 ≥1 free-space)。**诚实限制**:拉取产物里没有 SfM 每点光度 support(`sfm_sparse.ply` 只有 xyz+rgb;`sfm_live.db` 是特征/匹配库无 points3D),故 SfM 无法做忠实净票 support 项;这里只报 opposition,并指出设备端已对 SfM 云跑过 free-space 仲裁(`ghost_arbitration.json`)。

## 4. 产物(全绝对路径见 SHA256SUMS.txt)
- `merrell_netvote_prototype.py` — 主分析(确定性,自校验 union SHA)。
- `render_viewer.py` — 只读 `netvote_candidates.ply` 出图。
- `netvote_candidates.ply` — 13,488 点,每点附 `support / freespace_opposition / occlusion / agreement / l1_observations / netvote / in_roi`。
- `roi_all.ply` 与 `roi_netvote_survivors.ply` — **字节大小相同**,直观证明净票对 ROI 零删除。
- `rescued_true_floor.ply` — 364 个被净票救回的真地板点。
- `viewer_netvote_panels.png` — 四联图(A 全景 / B 椅子净票=0删 / C 椅子一票定罪 / D 真点误杀救回)。
- `stats.json` — 全部数字含 τ 敏感性与 verdict 串。

## 5. 复跑
```sh
/opt/homebrew/bin/python3.11 experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/merrell_netvote_prototype.py
/opt/homebrew/bin/python3.11 experiments/u3_merge_prototypes_2026-07-18/04_merrell_netvote/render_viewer.py
```

## 6. 未裁决(留用户签决)
- 本目录**不作出生/删除决定**,不声称"修好"。净票作为"去误杀护栏"可 accept(治一票定罪的误杀是实测有效的),但**明确 reject 净票作为椅子压扁解**。
- 治压扁需上游动刀(与 #5 同结论,二选一,均有损/改机制,须签决):给 plane-sweep 加离面深度竞争(`depth_competition_offsets_m` 现为空 → 填非零 offset 让椅子深度与地板深度竞争 ZNCC),或引入真正每视独立深度图再融合。
