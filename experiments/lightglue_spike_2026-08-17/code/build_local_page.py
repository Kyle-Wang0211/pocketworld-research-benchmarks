#!/usr/bin/env python3
"""本地拼并排页 —— 不再从租的机器搬整页。

背景:那台实例的**下行只有 ~25 KB/s**(上行 3.1 MB/s,严重不对称),
搬一个 7MB 的页要 5 分钟。而本地那份 compare_cuda_5090.html 里已经嵌着
CONTROL / B2 / B2+剪枝 / RaCo 四朵云的 base64,只有 P16k 是新的
⇒ 只搬 P16k(量化+莫顿序 delta+gzip,1.6MB),其余就地复用。

坐标一律量化成 uint16 交给 GPU 反量化(normalized 属性),页面体积对半砍。
⚠️ 这**不是降采样**:一个点都没少,只是坐标精度降到亚毫米,肉眼和我们的
重投影口径都远在其上。
"""
import base64, gzip, json, re, sys
from pathlib import Path

import numpy as np

SRC = Path("compare_cuda_5090.html")      # 已在本地、能打开的那份(含四朵云)

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--set", default="coverage", choices=["coverage", "raco", "ship", "df", "loftr", "four", "ext", "p_ctl", "p_loftr", "p_armA", "p_aliked", "budget", "fp16", "whodunit", "gate", "verdict", "preview", "union", "pose", "grow", "refply", "lever1"])
_cli = _ap.parse_args()

# 每页最多 4 窗:查看器在 9MB 与 14.4MB 之间有个上限,4 窗量化后约 6.6MB 是安全区
SETS = {
    # 覆盖之争:预算翻倍 vs 换检测器
    "coverage": ("compare_5arm.html", [
        ("基线",           "html:基线",      "DSP-SIFT 点 + 暴力匹配 ratio 0.8"),
        ("B2+剪枝 8192",   "html:B2+剪枝",   "ALIKED 8192 + 自适应剪枝 — 21.4 ms/对,覆盖 1.00×(基准)"),
        ("RaCo 8192",      "html:RaCo",      "RaCo 检测器 + ALIKED 描述 — 覆盖 1.16×,轨迹 4.74 更薄"),
        ("B2+剪枝 16384",  "bin:p16k",       "只把关键点预算翻倍 — 覆盖 1.35× 且轨迹升到 5.44"),
    ]),
    # RaCo 三兄弟:原版 / 协方差选点 / 排序器
    # 产品视角:能上机的两条 + 上不了机的天花板参照
    "ship": ("compare_ship.html", [
        ("基线(生产)",      "html:基线",   "同样的 SIFT 点 + 暴力匹配 ratio 0.8 —— 现在出货的样子"),
        ("臂A SIFT+LG",     "bin:armA",    "同样的 SIFT 点,只换匹配器 —— 覆盖 1.66×,28.4ms/对,✅能上机"),
        ("B2 ALIKED 8192",  "html:B2+剪枝", "换 ALIKED 前端 —— 覆盖 1.51×(反而不如臂A),❌前端 6.38GB"),
        ("RaCo 16384 天花板", "bin:r16kp",  "内存不是问题时的上限 —— 覆盖 2.55×,❌上不了机"),
    ]),
    # detector-free 重量:07-13 的三条质量论据里,选区可分性因鬼层解决而失效,
    # 但 track 闭合(架构性)仍然成立。这一组是 08-17 同机同口径重跑。
    "df": ("compare_detectorfree.html", [
        ("基线(生产)",   "bin:ctl",    "DSP-SIFT + 暴力匹配 — 覆盖 1.00×,轨迹 4.11,重投影 1.4188"),
        ("臂A SIFT+LG",  "bin:armA2",  "同样 SIFT 点只换匹配器 — 覆盖 1.68×,轨迹 4.15,✅能上机"),
        ("ALIKED 16384", "bin:p16k2",  "覆盖 2.03× 但点/格 3.36(往老地方加密),轨迹 5.45 最厚"),
        ("LoFTR-indoor", "bin:loftr8", "覆盖 2.70× 最高且点/格 2.16(铺新地方),但轨迹中位仅 2"),
    ]),
    # LoFTR 四档合并法:天花板卡在轨迹 2.95,换合并算法推不动 ⇒ 架构问题非实现问题
    "loftr": ("compare_loftr.html", [
        ("网格 cell=8",  "bin:loftr8", "硬网格合并 — 193,796 点,轨迹 2.95,≥3观测 48.3%"),
        ("KDTree r=4",   "bin:lk4",    "半径合并(无边界病)— 201,376 点,轨迹 2.95,≥3观测 48.4%"),
        ("KDTree r=8",   "bin:lk8",    "合并更狠 — 170,354 点,轨迹 2.87(反而更差)"),
        ("KDTree r=16",  "bin:lk16",   "合并最狠 — 111,564 点,轨迹 2.56,坐标被抹糊后 track 被门杀掉"),
    ]),
    # 用户指定顺序:基线 / LoFTR / 臂A / ALIKED@16384
    "four": ("compare_four.html", [
        ("基线(生产)",    "bin:ctl",    "DSP-SIFT + 暴力匹配 — 64,256 点,覆盖 1.00×,轨迹中位 3"),
        ("LoFTR-indoor",  "bin:loftr8", "detector-free — 193,796 点,覆盖 2.70×(最高),轨迹中位 2"),
        ("臂A SIFT+LG",   "bin:armA2",  "同样 SIFT 点只换匹配器 — 127,511 点,覆盖 1.68×,✅唯一能上机"),
        ("ALIKED 16384",  "bin:p16k2",  "238,545 点,覆盖 2.03×,轨迹 5.45 最扎实,❌内存+算力两道墙"),
    ]),
    # track 延长之后的四臂(Dense-SfM 式重投影认领 + BA,延长只加观测不加点)
    "ext": ("compare_ext.html", [
        ("基线+延长",     "bin:ctl_e",   "64,255 点 覆盖1.00× 轨迹中位4 ≥3观测83.9% 重投影1.3487(延长前 3/69.2%/1.4188)"),
        ("LoFTR+延长",    "bin:loftr_e", "201,371 点 覆盖2.71× 轨迹中位4 ≥3观测84.8% 重投影1.3036(延长前 2/48.4%/1.4247)"),
        ("臂A+延长",      "bin:armA_e",  "127,511 点 覆盖1.68× 轨迹中位3 ≥3观测71.4% 重投影1.3825"),
        ("ALIKED16k+延长", "bin:p16k_e", "238,545 点 覆盖2.03× 轨迹中位4 ≥3观测78.8% 重投影1.5146"),
    ]),
    # 四组两两对比:同一条臂的「延长前 vs 延长后」,单变量就是 track 延长这一刀。
    # ⚠️ LoFTR 用的是 KDTree r=4 那条(lk4),不是网格 cell=8 —— 延长跑在 LK4 上,
    #    拿网格那条当"前"就不是同一条臂了。
    "p_ctl": ("pair_baseline.html", [
        ("基线 延长前", "bin:ctl",   "64,256 点 · 观测 264,004 · 轨迹中位 3 · ≥3观测 69.2% · 重投影 1.4188"),
        ("基线 延长后", "bin:ctl_e", "64,255 点 · 观测 318,205 · 轨迹中位 4 · ≥3观测 83.9% · 重投影 1.3487"),
    ]),
    "p_loftr": ("pair_loftr.html", [
        ("LoFTR 延长前", "bin:lk4b",     "201,376 点 · 观测 594,840 · 轨迹中位 2 · ≥3观测 48.4% · 重投影 1.4247"),
        ("LoFTR 延长后", "bin:loftr_e", "201,371 点 · 观测 922,944 · 轨迹中位 4 · ≥3观测 84.8% · 重投影 1.3036"),
    ]),
    "p_armA": ("pair_armA.html", [
        ("臂A 延长前", "bin:armA2",  "127,511 点 · 观测 528,936 · 轨迹中位 3 · ≥3观测 59.0% · 重投影 1.4207"),
        ("臂A 延长后", "bin:armA_e", "127,511 点 · 观测 577,663 · 轨迹中位 3 · ≥3观测 71.4% · 重投影 1.3825"),
    ]),
    "p_aliked": ("pair_aliked.html", [
        ("ALIKED16k 延长前", "bin:p16k2",  "238,545 点 · 观测 1,300,261 · 轨迹中位 3 · ≥3观测 69.4% · 重投影 1.5513"),
        ("ALIKED16k 延长后", "bin:p16k_e", "238,545 点 · 观测 1,388,332 · 轨迹中位 4 · ≥3观测 78.8% · 重投影 1.5146"),
    ]),
    # 关键点预算之争:唯一变量是 max-kpts,其余(1600 分辨率/fp16 提取/自适应剪枝)全同
    "budget": ("compare_budget.html", [
        ("ALIKED @8192",  "ply:ply_P8K",  "133,228 点 · 观测 694,042 · 轨迹中位 3 · ≥3观测 69.1% · 重投影 1.5279 · 匹配 25.0 ms/对"),
        ("ALIKED @16384", "ply:ply_P16K", "238,545 点 · 观测 1,300,261 · 轨迹中位 3 · ≥3观测 69.4% · 重投影 1.5513 · 匹配 50.5 ms/对"),
    ]),
    # fp16 匹配器无损验证:唯一变量是匹配器精度(提取端两边都已是 fp16)
    "fp16": ("compare_fp16.html", [
        ("fp32 匹配器", "ply:ply_P16K",  "238,545 点 · 观测 1,300,261 · ≥3观测 69.4% · 重投影 1.5513 · 50.5 ms/对"),
        ("fp16 匹配器", "ply:ply_P16KH", "237,914 点 · 观测 1,297,792 · ≥3观测 69.3% · 重投影 1.5494 · 43.2 ms/对(1.17×)"),
    ]),
    # 谁的功劳:同样的 ALIKED@16384 点,唯一变量是匹配器
    "whodunit": ("compare_whodunit.html", [
        ("基线",              "html:基线",     "DSP-SIFT + 暴力 ratio0.8 — 64,059 点(现在出货的样子)"),
        ("ALIKED+暴力",       "ply:ply_BF16K", "同 ALIKED 点,暴力互检 ratio0.8 — 70,999 点 · 覆盖只有 LightGlue 的 0.34× · 2.44 ms/对"),
        ("ALIKED+LightGlue",  "ply:ply_P16KH", "同 ALIKED 点,LightGlue — 237,914 点 · 43.2 ms/对 ⇒ 惊艳来自匹配器"),
    ]),
    # 攻破 LightGlue:同 ALIKED 点,三种匹配器 + 参照
    "gate": ("compare_gate.html", [
        ("ALIKED+暴力",       "ply:ply_BF16K", "无先验互检 ratio0.8 — 70,999 点 · 2.44 ms/对 · 覆盖0.34×(塌)"),
        ("ALIKED+极线门",     "ply:ply_GT16K", "AR位姿门内互检 ratio0.95 — 292,364 点 · 9.16 ms/对 · 覆盖1.34-3.92× ⚠️肉眼判浮点"),
        ("ALIKED+LightGlue",  "ply:ply_P16KH", "9层transformer — 237,914 点 · 43.2 ms/对 · 参照系"),
    ]),
    # 终审:两条官方口径 + 三件套 vs LightGlue
    "verdict": ("compare_verdict.html", [
        ("GTO(ORB-SLAM口径)", "ply:ply_GTO",      "1.96px/ratio0.6 — 132,236 点 · ≥3观测70.5% · 重投影1.1563(全场最佳) · 10.2 ms/对"),
        ("GTC(COLMAP口径)",   "ply:ply_GTC",      "4px/0.8/cos0.765 — 136,143 点 · ≥3观测76.1% · 最保守 · 9.2 ms/对"),
        ("三件套(宽门+延长+过滤)", "ply:ply_GT16KEf3", "197,487 点 · 覆盖0.88-1.89× · 9.2ms+finalize · 残余散点待判"),
        ("ALIKED+LightGlue",   "ply:ply_P16KH",    "参照 — 237,914 点 · ≥3观测69.3% · 重投影1.5494 · 43.2 ms/对"),
    ]),
    # 用户提议:预览云=抽稀稠密?同点数公平对比"最好的稀疏 vs 抽走99.2%的稠密"
    "preview": ("compare_preview.html", [
        ("ALIKED+LightGlue稀疏", "ply:ply_P16KH",    "最好的稀疏 — 237,914 点 · 43.2 ms/对匹配"),
        ("抽稀稠密·同点数",       "ply:ds_dense_238k", "CasDiffMVS 30.6M 随机抽到 237,914 点(0.78%) — 零匹配算力,搭稠密便车"),
        ("抽稀稠密·1M",          "ply:ds_dense_1m",   "同稠密抽到 1,000,000 点(3.3%) — 预览上限参考"),
        ("GTO稀疏(位姿专用)",    "ply:ply_GTO",      "ORB-SLAM口径门控 — 132,236 点 · 位姿全场最准 · 10.2 ms/对"),
    ]),
    # 并集提案:稠密主体 + 稀疏补外围,按格帽密度
    "union": ("compare_union.html", [
        ("ALIKED+LightGlue稀疏", "ply:ply_P16KH", "237,914 点 — 外围广但内部空(白墙铺不上)"),
        ("抽稀稠密·同点数",       "ply:ds_dense_238k", "237,914 点 — 内部实心但外围被融合门砍掉"),
        ("并集(稠密主体+稀疏补丁)", "ply:ds_union", "293,920 点 = 抽稀稠密 + 56,006 稀疏点只填稠密空缺格(帽4点/格保均匀)"),
    ]),
    # 终极单变量:唯一差异是位姿引擎(LightGlue vs GTO门控)。噪声同种子/口径全同/同seed抽稀
    "pose": ("compare_pose.html", [
        ("稠密 @ LightGlue位姿", "ply:ds_dense_238k",     "现状 — 30,640,053 点抽到 237,914 · 匹配 43.2 ms/对"),
        ("稠密 @ GTO位姿",       "ply:ds_dense_gto_238k", "改后 — 30,882,294 点(+0.79%,噪声地板内)抽到 237,914 · 匹配 10.2 ms/对"),
    ]),
    # 拍摄进度四连拍:实测冻结调度下,用户在 t 步看到的稠密(尾随相机生长)
    "grow": ("compare_grow.html", [
        ("拍到 25%(t=33)",  "ply:grow_t33",  "已融 15/132 帧 · 3.1M 点(显示抽稀 18万) — 最早的块 t=22 出现"),
        ("拍到 50%(t=66)",  "ply:grow_t66",  "已融 54/132 帧 · 12.2M 点 — 稠密尾随扫过的区域长出来"),
        ("拍到 75%(t=99)",  "ply:grow_t99",  "已融 79/132 帧 · 17.7M 点"),
        ("拍完+收尾",        "ply:grow_t132", "132/132 · 30.6M 点 — 与官方全量逐字节一致(MD5已证)"),
    ]),
    # 参照对拍真彩版:同 1/24 采样率,窗口间密度差=真实密度差
    "refply": ("compare_refply.html", [
        ("CasDiffMVS(生产管线)", "ply:ref_cas_r24",  "30.6M 点抽 1/24=1,276,668 — 覆盖满,墙后偏移雾 4.13%"),
        ("OpenMVS 参照(AGPL仅诊断)", "ply:ref_omvs_r24", "4.0M 点抽 1/24=165,536 — 雾 1.89% 墙更紧,但无纹理段大片空"),
    ]),
    # 杠杆①终审:同 1/24 采样率,唯一变量=9 个雾帧的源选择(跨走廊)
    "lever1": ("compare_lever1.html", [
        ("现状(官方选源)",   "ply:ref_cas_r24", "30.64M 抽 1/24 — 墙后雾 42,285 点(4.13%)"),
        ("杠杆①选源改造后", "ply:lever1_r24",  "30.19M 抽 1/24 — 雾 2,167(−94.9%) · 墙面 +7.9% · 只重推 11 帧"),
    ]),
    "raco": ("compare_raco.html", [
        ("B2+剪枝 8192",   "html:B2+剪枝",   "参照系 — 覆盖 1.00×,轨迹 5.21,重投影 1.5266"),
        ("RaCo 8192",      "html:RaCo",      "bypass 取前 8192 — 覆盖 1.16×,轨迹 4.74"),
        ("RaCo+协方差",    "bin:rcov",       "16384 候选取 σ 最小的 8192 — 重投影最低 1.5106,覆盖回落 1.08×"),
        ("RaCo+排序器",    "bin:rrank",      "开 dense ranker — 轨迹跌到 4.57,观测 −5.4%,四项全跌"),
    ]),
}
OUT_NAME, PLAN = SETS[_cli.set]
OUT = Path(OUT_NAME)


# 窗口左下角那张小表(数字来自各臂 metrics.json / coverage_metric.py,手抄一次集中在这里)
STATS = {
    "基线(生产)":      dict(pts="64,059",  obs="263,589", tl="4.11", rp="1.4191", cov="1.00×"),
    "臂A SIFT+LG":     dict(pts="126,508", obs="527,495", tl="4.17", rp="1.4206", cov="1.66×"),
    "B2 ALIKED 8192":  dict(pts="133,646", obs="695,664", tl="5.21", rp="1.5266", cov="1.51×"),
    "RaCo 16384 天花板": dict(pts="269,716", obs="1,265,896", tl="4.69", rp="1.5236", cov="2.55×"),
    "基线(生产)":   dict(pts="64,256",  obs="264,004", tl="4.11", rp="1.4188", cov="1.00×"),
    "臂A SIFT+LG":  dict(pts="127,511", obs="528,936", tl="4.15", rp="1.4207", cov="1.68×"),
    "ALIKED 16384": dict(pts="238,545", obs="1,300,261", tl="5.45", rp="1.5513", cov="2.03×"),
    "LoFTR-indoor": dict(pts="193,796", obs="571,136", tl="2.95", rp="1.4295", cov="2.70×"),
    "网格 cell=8": dict(pts="193,796", obs="571,136", tl="2.95", rp="1.4295", cov="2.70×"),
    "KDTree r=4":  dict(pts="201,376", obs="594,840", tl="2.95", rp="1.4247", cov="—"),
    "KDTree r=8":  dict(pts="170,354", obs="488,198", tl="2.87", rp="1.4325", cov="—"),
    "KDTree r=16": dict(pts="111,564", obs="286,069", tl="2.56", rp="1.4534", cov="—"),
    "基线+延长":      dict(pts="64,255",  obs="318,205", tl="4.95", rp="1.3487", cov="1.00×"),
    "LoFTR+延长":     dict(pts="201,371", obs="922,944", tl="4.58", rp="1.3036", cov="2.71×"),
    "臂A+延长":       dict(pts="127,511", obs="577,663", tl="4.53", rp="1.3825", cov="1.68×"),
    "ALIKED16k+延长": dict(pts="238,545", obs="1,388,332", tl="5.82", rp="1.5146", cov="2.03×"),
    "基线 延长前": dict(pts="64,256",  obs="264,004", tl="4.11", rp="1.4188", cov="1.00×"),
    "基线 延长后": dict(pts="64,255",  obs="318,205", tl="4.95", rp="1.3487", cov="1.00×"),
    "LoFTR 延长前": dict(pts="201,376", obs="594,840", tl="2.95", rp="1.4247", cov="2.70×"),
    "LoFTR 延长后": dict(pts="201,371", obs="922,944", tl="4.58", rp="1.3036", cov="2.71×"),
    "臂A 延长前": dict(pts="127,511", obs="528,936", tl="4.15", rp="1.4207", cov="1.68×"),
    "臂A 延长后": dict(pts="127,511", obs="577,663", tl="4.53", rp="1.3825", cov="1.68×"),
    "ALIKED16k 延长前": dict(pts="238,545", obs="1,300,261", tl="5.45", rp="1.5513", cov="2.03×"),
    "ALIKED16k 延长后": dict(pts="238,545", obs="1,388,332", tl="5.82", rp="1.5146", cov="2.03×"),
    "ALIKED @8192":  dict(pts="133,228", obs="694,042",   tl="5.21", rp="1.5279", cov="—"),
    "ALIKED @16384": dict(pts="238,545", obs="1,300,261", tl="5.45", rp="1.5513", cov="—"),
    "ALIKED+暴力":      dict(pts="70,999",  obs="306,354",   tl="4.31", rp="1.4258", cov="0.34×"),
    "ALIKED+LightGlue": dict(pts="237,914", obs="1,297,792", tl="5.45", rp="1.5494", cov="1.00×"),
    "ALIKED+极线门":    dict(pts="292,364", obs="1,238,478", tl="4.24", rp="1.4450", cov="1.34×"),
    "GTO(ORB-SLAM口径)": dict(pts="132,236", obs="585,352", tl="4.43", rp="1.1563", cov="0.60-1.24×"),
    "GTC(COLMAP口径)":   dict(pts="136,143", obs="624,041", tl="4.58", rp="1.4371", cov="0.61-0.77×"),
    "三件套(宽门+延长+过滤)": dict(pts="197,487", obs="—", tl="—", rp="—", cov="0.88-1.89×"),
    "ALIKED+LightGlue稀疏": dict(pts="237,914", obs="1,297,792", tl="5.45", rp="1.5494", cov="参照"),
    "抽稀稠密·同点数": dict(pts="237,914", obs="—", tl="—", rp="—", cov="0.78% 抽样"),
    "抽稀稠密·1M": dict(pts="1,000,000", obs="—", tl="—", rp="—", cov="3.3% 抽样"),
    "GTO稀疏(位姿专用)": dict(pts="132,236", obs="585,352", tl="4.43", rp="1.1563", cov="0.60-1.24×"),
    "并集(稠密主体+稀疏补丁)": dict(pts="293,920", obs="—", tl="—", rp="—", cov="0.05m并集"),
    "稠密 @ LightGlue位姿": dict(pts="237,914", obs="全量 30.64M", tl="—", rp="—", cov="参照"),
    "稠密 @ GTO位姿":       dict(pts="237,914", obs="全量 30.88M", tl="—", rp="—", cov="gauge残差2.08mm"),
    "拍到 25%(t=33)":  dict(pts="3.1M(融15帧)", obs="—", tl="—", rp="—", cov="—"),
    "拍到 50%(t=66)":  dict(pts="12.2M(融54帧)", obs="—", tl="—", rp="—", cov="—"),
    "拍到 75%(t=99)":  dict(pts="17.7M(融79帧)", obs="—", tl="—", rp="—", cov="—"),
    "拍完+收尾":        dict(pts="30.6M(全部)", obs="—", tl="—", rp="—", cov="MD5=官方"),
    "CasDiffMVS(生产管线)": dict(pts="1,276,668", obs="全量 30.6M", tl="—", rp="墙RMS 8.1mm", cov="雾 4.13%"),
    "OpenMVS 参照(AGPL仅诊断)": dict(pts="165,536", obs="全量 4.0M", tl="—", rp="墙RMS 6.7mm", cov="雾 1.89%"),
    "现状(官方选源)":   dict(pts="1,276,668", obs="全量 30.64M", tl="—", rp="雾 4.13%", cov="基准"),
    "杠杆①选源改造后": dict(pts="1,257,811", obs="全量 30.19M", tl="—", rp="雾 0.21%", cov="覆盖损失全在地板内"),
    "fp32 匹配器": dict(pts="238,545", obs="1,300,261", tl="5.45", rp="1.5513", cov="1.000×"),
    "fp16 匹配器": dict(pts="237,914", obs="1,297,792", tl="5.45", rp="1.5494", cov="0.998×"),
    "基线":          dict(pts="64,059",  obs="263,589",   tl="4.11", rp="1.4191", cov="0.66×"),
    "B2+剪枝 8192":  dict(pts="133,646", obs="695,664",   tl="5.21", rp="1.5266", cov="1.00×"),
    "RaCo 8192":     dict(pts="141,642", obs="671,739",   tl="4.74", rp="1.5266", cov="1.16×"),
    "RaCo+协方差":   dict(pts="139,479", obs="665,549",   tl="4.77", rp="1.5106", cov="1.08×"),
    "RaCo+排序器":   dict(pts="139,041", obs="635,403",   tl="4.57", rp="1.5261", cov="1.20×"),
    "B2+剪枝 16384": dict(pts="238,980", obs="1,299,449", tl="5.44", rp="1.5502", cov="1.35×"),
}


def clouds_from_html(p: Path):
    m = re.search(r"const CLOUDS=(\[.*?\]), VIEW=", p.read_text(), re.S)
    if not m:
        sys.exit(f"没能从 {p} 里解析出 CLOUDS")
    out = []
    for c in json.loads(m.group(1)):
        xyz = np.frombuffer(base64.b64decode(c["xyz"]), dtype="<f4").reshape(-1, 3)
        rgb = np.frombuffer(base64.b64decode(c["rgb"]), dtype=np.uint8).reshape(-1, 3)
        out.append((c["name"], c["sub"], xyz, rgb))
    return out


def load_new(p: Path):
    """远端打包格式:lo(3f4) span(3f4) n(i4) + uint16 delta 坐标 + rgb。"""
    b = gzip.decompress(p.read_bytes())
    lo = np.frombuffer(b[0:12], dtype="<f4")
    span = np.frombuffer(b[12:24], dtype="<f4")
    n = int(np.frombuffer(b[24:28], dtype="<i4")[0])
    d = np.frombuffer(b[28:28 + n * 6], dtype="<u2").reshape(n, 3)
    rgb = np.frombuffer(b[28 + n * 6:28 + n * 9], dtype=np.uint8).reshape(n, 3)
    q = np.cumsum(d.astype(np.int64), axis=0).astype(np.uint16)   # delta 还原
    return lo + q.astype(np.float64) / 65535.0 * span, rgb


def load_ply(p: Path):
    """直读 export_ply.py 写出的二进制 PLY(xyz f4 + rgb u1)。"""
    with p.open("rb") as f:
        hdr = b""
        while True:
            l = f.readline(); hdr += l
            if l.strip() == b"end_header":
                break
        n = int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1])
        dt = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                       ("r", "u1"), ("g", "u1"), ("b", "u1")])
        d = np.frombuffer(f.read(n * dt.itemsize), dtype=dt, count=n)
    xyz = np.stack([d["x"], d["y"], d["z"]], 1).astype(np.float64)
    rgb = np.stack([d["r"], d["g"], d["b"]], 1)
    return xyz, rgb


def main():
    from_html = {c[0]: (c[2], c[3]) for c in clouds_from_html(SRC)}
    keep = []
    for label, src, _sub in PLAN:
        kind, key = src.split(":", 1)
        if kind == "html":
            if key not in from_html:
                sys.exit(f"源页里没有 “{key}”,现有:{list(from_html)}")
            xyz, rgb = from_html[key]
        elif kind == "ply":
            xyz, rgb = load_ply(Path(key + ".ply"))
        else:
            xyz, rgb = load_new(Path(key + ".bin.gz"))
        keep.append((label, xyz, rgb))

    lo = np.min([x.min(0) for _, x, _ in keep], axis=0)
    span = np.maximum(np.max([x.max(0) for _, x, _ in keep], axis=0) - lo, 1e-6)
    print(f"量化步长 {(span / 65535 * 1000).round(3).tolist()} mm/轴")

    SUB = {l: d for l, _s, d in PLAN}
    clouds = []
    for nm, x, c in keep:
        q = np.round((x - lo) / span * 65535).clip(0, 65535).astype("<u2")
        clouds.append(dict(name=nm, sub=SUB[nm], n=len(x),
                           xyz=base64.b64encode(q.tobytes()).decode(),
                           rgb=base64.b64encode(np.ascontiguousarray(c).tobytes()).decode()))
        print(f"{nm}: {len(x):,} 点")

    ref = keep[min(1, len(keep) - 1)][1]
    ctr = np.median(ref, 0)
    view = dict(cx=float(ctr[0]), cy=float(ctr[1]), cz=float(ctr[2]),
                radius=float(np.percentile(np.linalg.norm(ref - ctr, axis=1), 95)),
                lo=lo.astype(float).tolist(), span=span.astype(float).tolist())

    OUT.write_text(TEMPLATE.replace("__DATA__", json.dumps(clouds))
                   .replace("__VIEW__", json.dumps(view))
                   .replace("__NCOL__", str(len(clouds)))
                   .replace("__STATS__", json.dumps(STATS)))
    print(f"已写出 {OUT}  {OUT.stat().st_size / 1e6:.1f} MB")


TEMPLATE = r"""<!doctype html>
<meta charset="utf-8">
<title>覆盖对比 — 四臂并排</title>
<style>
  :root{--bg:#0e0f12;--fg:#e8e8ea;--dim:#9aa0a6;--line:#26282e}
  html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
    font:13px/1.5 -apple-system,"PingFang SC",sans-serif}
  header{padding:10px 14px;border-bottom:1px solid var(--line)}
  h1{font-size:15px;margin:0 0 6px}
  .hint{color:var(--dim);font-size:12px}
  .ctl{display:flex;gap:16px;align-items:center;margin-top:8px;flex-wrap:wrap}
  .ctl label{color:var(--dim)}
  #grid{display:grid;grid-template-columns:repeat(__NCOL__,1fr);gap:1px;background:var(--line);
    height:calc(100% - 118px)}
  .pane{position:relative;background:var(--bg);overflow:hidden}
  canvas{display:block;width:100%;height:100%}
  .cap{position:absolute;top:0;left:0;right:0;padding:8px 10px;
    background:linear-gradient(#0e0f12ee,#0e0f1200);pointer-events:none}
  .cap b{font-size:13px}
  .cap div{color:var(--dim);font-size:11px}
  table{position:absolute;bottom:8px;left:10px;background:#0e0f12cc;padding:6px 8px;
    border-radius:4px;font-size:11px;color:var(--dim);border-collapse:collapse;pointer-events:none}
  td{padding:1px 8px 1px 0} td.v{color:var(--fg)}
</style>
<header>
  <h1>覆盖对比 — b28(132 帧,同一场拍摄,全部在同一张 5090 上产出)</h1>
  <div class="hint">拖拽旋转 · 滚轮缩放 · 右键平移 —— 四窗相机同步。已用相机光心统一 gauge(相似变换保形)。坐标按亚毫米量化以压体积,点一个没少。</div>
  <div class="ctl"><label>点大小 <input id="ps" type="range" min="1" max="6" step="0.5" value="2"></label></div>
</header>
<div id="grid"></div>
<script>
const CLOUDS=__DATA__, VIEW=__VIEW__, STATS=__STATS__;
const b64=s=>{const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return u};
const cam={az:0.6,el:0.35,dist:VIEW.radius*2.4,tx:VIEW.cx,ty:VIEW.cy,tz:VIEW.cz};
const VS=`attribute vec3 p;attribute vec3 c;uniform mat4 mvp;uniform float ps;
uniform vec3 lo;uniform vec3 span;varying vec3 vc;
void main(){gl_Position=mvp*vec4(lo+p*span,1.0);gl_PointSize=ps;vc=c;}`;
const FS=`precision mediump float;varying vec3 vc;
void main(){vec2 d=gl_PointCoord-vec2(0.5);if(dot(d,d)>0.25)discard;gl_FragColor=vec4(vc,1.0);}`;
function sh(gl,t,s){const o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);
  if(!gl.getShaderParameter(o,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(o);return o}
function mul(a,b){const o=new Float32Array(16);
  for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;for(let k=0;k<4;k++)s+=a[k*4+j]*b[i*4+k];o[i*4+j]=s}return o}
function persp(f,as,n,fa){const t=1/Math.tan(f/2);return new Float32Array(
  [t/as,0,0,0, 0,t,0,0, 0,0,(fa+n)/(n-fa),-1, 0,0,2*fa*n/(n-fa),0])}
function lookAt(e,c,u){const z=norm(sub(e,c)),x=norm(cross(u,z)),y=cross(z,x);
  return new Float32Array([x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0,
    -dot(x,e),-dot(y,e),-dot(z,e),1])}
const sub=(a,b)=>[a[0]-b[0],a[1]-b[1],a[2]-b[2]], dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const norm=a=>{const l=Math.hypot(...a)||1;return [a[0]/l,a[1]/l,a[2]/l]};

const panes=CLOUDS.map(cl=>{
  const d=document.createElement('div');d.className='pane';
  const s=STATS[cl.name]||{};
  d.innerHTML=`<canvas></canvas><div class="cap"><b>${cl.name}</b><div>${cl.sub}</div></div>
   <table>
    <tr><td>点数</td><td class="v">${s.pts||cl.n}</td></tr>
    <tr><td>观测</td><td class="v">${s.obs||''}</td></tr>
    <tr><td>轨迹均值</td><td class="v">${s.tl||''}</td></tr>
    <tr><td>覆盖(0.2m 体素)</td><td class="v">${s.cov||''}</td></tr>
    <tr><td>重投影 px</td><td class="v">${s.rp||''}</td></tr>
   </table>`;
  document.getElementById('grid').appendChild(d);
  const cv=d.querySelector('canvas'), gl=cv.getContext('webgl',{antialias:true});
  const pr=gl.createProgram();
  gl.attachShader(pr,sh(gl,gl.VERTEX_SHADER,VS));gl.attachShader(pr,sh(gl,gl.FRAGMENT_SHADER,FS));
  gl.linkProgram(pr);gl.useProgram(pr);
  const xyz=new Uint16Array(b64(cl.xyz).buffer), rgb=b64(cl.rgb);
  const bp=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bp);gl.bufferData(gl.ARRAY_BUFFER,xyz,gl.STATIC_DRAW);
  const ap=gl.getAttribLocation(pr,'p');gl.enableVertexAttribArray(ap);
  gl.vertexAttribPointer(ap,3,gl.UNSIGNED_SHORT,true,0,0);
  const bc=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,bc);gl.bufferData(gl.ARRAY_BUFFER,rgb,gl.STATIC_DRAW);
  const ac=gl.getAttribLocation(pr,'c');gl.enableVertexAttribArray(ac);
  gl.vertexAttribPointer(ac,3,gl.UNSIGNED_BYTE,true,0,0);
  gl.uniform3fv(gl.getUniformLocation(pr,'lo'),VIEW.lo);
  gl.uniform3fv(gl.getUniformLocation(pr,'span'),VIEW.span);
  gl.enable(gl.DEPTH_TEST);gl.clearColor(0.055,0.059,0.071,1);
  return {cv,gl,pr,n:cl.n,uMvp:gl.getUniformLocation(pr,'mvp'),uPs:gl.getUniformLocation(pr,'ps')};
});

let ps=2;
document.getElementById('ps').oninput=e=>ps=+e.target.value;
function draw(){
  const ce=[cam.tx+cam.dist*Math.cos(cam.el)*Math.sin(cam.az),
            cam.ty+cam.dist*Math.sin(cam.el),
            cam.tz+cam.dist*Math.cos(cam.el)*Math.cos(cam.az)];
  for(const p of panes){
    const w=p.cv.clientWidth,h=p.cv.clientHeight,dpr=Math.min(devicePixelRatio,2);
    if(p.cv.width!==w*dpr){p.cv.width=w*dpr;p.cv.height=h*dpr}
    p.gl.viewport(0,0,p.cv.width,p.cv.height);
    p.gl.clear(p.gl.COLOR_BUFFER_BIT|p.gl.DEPTH_BUFFER_BIT);
    p.gl.useProgram(p.pr);
    const mvp=mul(persp(1.0,w/h,VIEW.radius*0.005,VIEW.radius*40),
                  lookAt(ce,[cam.tx,cam.ty,cam.tz],[0,1,0]));
    p.gl.uniformMatrix4fv(p.uMvp,false,mvp);p.gl.uniform1f(p.uPs,ps*dpr);
    p.gl.drawArrays(p.gl.POINTS,0,p.n);
  }
  requestAnimationFrame(draw);
}
let drag=null;
addEventListener('mousedown',e=>{if(e.target.tagName==='CANVAS'){drag={x:e.clientX,y:e.clientY,b:e.button};e.preventDefault()}});
addEventListener('mouseup',()=>drag=null);
addEventListener('contextmenu',e=>{if(e.target.tagName==='CANVAS')e.preventDefault()});
addEventListener('mousemove',e=>{
  if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.x=e.clientX;drag.y=e.clientY;
  if(drag.b===2){const k=cam.dist*0.0015;
    cam.tx-=k*(dx*Math.cos(cam.az)); cam.tz+=k*(dx*Math.sin(cam.az)); cam.ty+=k*dy;}
  else{cam.az-=dx*0.006;cam.el=Math.max(-1.5,Math.min(1.5,cam.el+dy*0.006));}
});
addEventListener('wheel',e=>{if(e.target.tagName==='CANVAS'){
  cam.dist*=Math.exp(e.deltaY*0.001);e.preventDefault()}},{passive:false});
draw();
</script>
"""

if __name__ == "__main__":
    main()
