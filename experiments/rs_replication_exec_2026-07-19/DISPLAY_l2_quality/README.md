# 显示纪律肉眼件(2026-07-18 深夜,应用户"L2+quality 没看过也没批过装机"要求)

- `l2_view_cap5x.ply`:设备交付云套用**装机 L2 语义**(hidden = ghost_view_mask bit1(band15) ∧ ¬bit5(rescued))后的显示态。cap50 隐藏 5,283/92,849(5.7%),cap51 隐藏 4,454/64,392(6.9%)。掩码与交付 PLY 逐点对齐(len 断言)。
- `quality_view_cap5x.ply`:**quality 重着色提案预览(E18,未装机)**,RS quality 模式语义适配:≥3 视 track=实色,2-view=降亮 35%。track 长度取自回放世界 points3D.bin(精确);设备云离线 obs 恢复饥饿 66% 不可用于此。cap50 降亮 70.1%,cap51 67.6%。
- ⚠️装机状态如实:L2 渲染门在设备默认开是 E17 发现的既成事实,**未经用户批准**;quality 重着色为纯提案。两者去留由用户看图后裁决。
- 生成器:make_views.py
