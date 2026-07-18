# 预览"不生"严谨方案(RS 机制复刻版,2026-07-19)

> 依据:R1/E2-C(RS 纪律 VERIFIED)、社区调研(GHOST_community_wisdom)、E2-E17 全部实证。
> 原则:只复刻 RS 实际有的机制,不发明 RS 没有的(十三战教训);每步先诊断后动刀。

## 一、RS 的"不生"= 三个机制(全部有据,非猜测)

| # | RS 机制 | 证据 | 我们的对应缺陷(实测) |
|---|---|---|---|
| **M-A** | **全局匹配 → 长 track**:云端算力对全图集配对,同一物理点的观测连成一条多视 track;多视三角化+BA 把深度钉死,σ_depth 无处成壳 | R1 VERIFIED(preselector/全对图);COLMAP 家族标准 | 窗口匹配(K_HOT=6+对数上限+热债)→ **65% track 是 2-view**(57,820/89,594),2-view 三角化残差恒≈0、深度全靠 σ_depth 抽签 → 壳 |
| **M-B** | **没有 BA 外出生通道**:每个发布点都活过完整对齐 BA+重投影裁剪 | R1 VERIFIED(BA 无绕过,Draft=显式降质开关) | **temporal_detail 在 BA 后直灌 ~18k 个永不精化的 2-view 点**(生产代码自注"born of low-parallax DLT depth noise")——RS 构造性没有这个病 |
| **M-C** | **证据弱处留洞/降色,不硬造**:弱纹理"may not be reconstructed at all";quality 模式全量重着色 | R1/E2-C VERIFIED | 我们激进恢复细节(temporal_detail 的存在理由就是补细节)= 拿 σ_dep 噪声换覆盖数字 |

## 二、两个从未跑过的关键实验(E19,先诊断后改革)

**E19-A 鬼带出生通道归因**(纯诊断,20 分钟级):
- E12 副本加 env 跳过 RestoreTemporalDetail → 回放 cap50/51 → 量鬼带/双峰/细节覆盖的 before/after。
- 回答:**鬼带里多少比例是 temporal_detail 生的、多少是 live/mapper 2-view 生的**——十三战从没做过这个归因(E13 量的是 site 共享,不是通道)。

**E19-B 匹配图增稠 = M-A 的正面复刻**(本方案的主菜):
- 把 E6 已验证的跨窗匹配对(cap50 48,226/cap51 28,224,当时是"注入成点",这次**注入进 db 匹配图**)写入 db 副本 → 回放 → union-find 的 track 天然变长 → 量:2-view 占比↓多少、鬼带/厚度/覆盖变化。
- 机制预期:原来的 2-view 碎片获得第三/第四视 → 多视三角化+BA 把深度拉回真面(**不是删鬼,是鬼根本不再以鬼的深度出生**)——这才是 RS 全局匹配的直接复刻,也是"产跨边"的匹配层原形态(vs E9 在出生闸层的错位尝试)。

## 三、归因后的通道改革(按 E19-A 结果定,三案备选,全部有出处)
- 案 1(RS 纪律):temporal_detail 出生移到 stage-2 BA 之前,活过 BA+裁剪才发布;
- 案 2(DSM reobservation):temporal_detail 候选须第三视确认才出生,否则 AMBIGUOUS 不发布;
- 案 3(RS quality 模式):照生,但按确定性分层显示(多视=实色,2-view 低确定=降色/暗显)——display-only,与 E6-B quality viewer/E18 会师。

## 四、收尾栈(已就位部分)
覆盖=v1.1(已批)+detector-free 集成;显示纪律=L2(装机已开)+E18 扩域+quality 分层;“不生”=本方案 E19→通道改革。

## 五、验收
每步同 gauge 真彩并排+用户肉眼;四把尺子+固定生产平面直尺;质量无损硬门;墙钟不增(E19-B 的匹配注入发生在 finalize 前的 db 层,回放量真实成本)。
