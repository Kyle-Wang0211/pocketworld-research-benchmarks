# Gipuma(GPL-3.0)血统取证 —— APDe-MVS → 我们的 WGSL 移植

日期:2026-08-16
结论:**不是阻断。** 唯一进到 kernel 侧的 GPL 片段已清除,并用字节比对证明行为不变。

---

## 0. 为什么要查

APDe-MVS 声明 MIT,但它的祖先 ACMM 在 README 里写着
"largely benefits from **Gipuma**",而 Gipuma 是 **GPL-3.0**。
**MIT 声明不能给 GPL 派生代码洗白** —— 如果 ACMM 抄了 Gipuma 的受保护表达,
整条链(ACMM → APD-MVS → APDe-MVS → 我们的移植)都会被传染。

所以问题不是"致谢里写了谁",而是**到底抄了哪几行、那几行有没有可版权性、
以及有没有流到我们要出货的代码里**。

## 1. 血统链(全部现场核实,非推断)

| 层 | 仓库 | 许可 | 与 gipuma 逐行相同 | 致谢点名 gipuma |
|---|---|---|---|---|
| 根 | kysucix/gipuma | 🔴 **GPL-3.0** | — | — |
| ↓ | GhiXu/**ACMH** | MIT (c) 2021 Qingshan Xu | **9.6%** (133/1383) | ✅ |
| ↓ | GhiXu/**ACMM** | MIT (c) 2019 Qingshan Xu | **9.7%** (170/1753) | ✅ |
| ↓ | GhiXu/**ACMP** | MIT (c) 2019 Qingshan Xu | **8.0%** (133/1655) | ✅ |
| ↓ | whoiszzj/**APD-MVS** | MIT (c) 2023 Zhaojie Zeng | 3.3% (91/2789) | ❌ 只写 ACMM |
| ↓ | whoiszzj/**APDe-MVS** ← 我们移植的 | MIT (c) 2025 Zhaojie Zeng | **2.9%** (98/3379) | ❌ 只写 ACMM |

⇒ **GPL→MIT 的断点在 ACMM 那一层**,不在 APD。
⇒ gipuma 这个名字**在 APD-MVS 那一代就从致谢里消失了**(而代码痕迹还在)。

口径:去空白、去注释后逐行完全相同;只统计长度 ≥12 字符的行(排除括号/单赋值噪声)。
工具见本文末尾。

## 2. APDe 里 ≥4 连续行的 gipuma 原文 —— 总共只有 5 处 3 类

| 位置 | 来源 | 内容 | 可版权性评估 |
|---|---|---|---|
| `APD.cu:6-9`、`17-20` | `gipuma.cu:684` | `sort_small` 插入排序两个重载 | 教科书算法,变量名 i/j/tmp |
| `main.h:11-22` | `globalstate.h:10` | `#include` 列表 11 行 | 无(功能性清单) |
| `APD.cpp:701-705`、`725-729` | `main.cpp:537` | CUDA `texDesc` 五行样板 | 无(CUDA API 固定写法) |

对照 —— ACMM 里抄得最重的两块,**APDe 已经重写**:
- gipuma 的 `.dmb` 二进制 I/O(`fwrite(&type,sizeof(int32_t),1,outimage)` …)
- gipuma 的 `fprintf` PLY 头写出 → APDe 改成 `out << "property float x\n"`

## 3. 没被抄的才是关键

Gipuma 的**整套架构**在 ACMM / APD 中**零出现**:

| gipuma 符号 | gipuma | ACMM | APD |
|---|---|---|---|
| `GlobalState` | 26 | 0 | 0 |
| `AlgorithmParameters` | 28 | 0 | 0 |
| `Managed`(统一内存基类) | 19 | 0 | 0 |
| `CameraParameters_cu` | 16 | 0 | 0 |
| `get3Dpoint` | 12 | 0 | 0 |
| `LineState` | 8 | 0 | 0 |
| `getCorrespondingPoint` | 7 | 0 | 0 |
| `getDepthFromPlane3_cu` | 2 | 0 | 0 |
| `COMB_BEST_N` | 5 | 0 | 0 |

⇒ **核心算法是独立重写的,不是改名的 Gipuma。**
被复用的全部是 I/O 辅助、API 样板和一个排序。

## 4. 落到我们身上 —— 唯一一条,已清除

2741 行 WGSL 中带 gipuma 血统的**只有 `sort_small`**。
其余三类都在 host 侧 C++,我们根本没移植。实测:

```
sort_small  6 命中(已清除) │ mul4 0 │ vecdiv4 0 │ texDesc 0 │ outputPly 0 │ dmb 0
```

完整性交叉检查:**80 个 WGSL 函数名逐个 grep gipuma 全仓 → 零命中。**

### 处理

`apde_init.wgsl` 的 `sort_small21/32` → 重写为**选择排序** `ascending_prefix21/32`,
独立实现,与上游无共同表达。

两处调用点都只要求 `[0,n)` 升序:
- `:99` 取 best-k 前缀和 + 阈值 `cv[top_k-1]`
- `:159` 取中值

对无 NaN 的有限浮点,任何正确升序排序输出相同。

### 验证(不是论证,是实测)

同一份 **138 帧内部自洽子集**、同一 host 载具,只换 metallib:

```
两版 bindings.txt          diff → 完全相同(证明只有排序变了)
depth_OLD.f32 vs NEW.f32   cmp  → ✅ 逐字节相同  md5 73b4a356…
conf_OLD.f32  vs NEW.f32   cmp  → ✅ 逐字节相同  md5 42f4a244…
```

非退化性核对(否则比对是虚的):
`非零深度 100%,深度 p50=5.596m,conf p50=0.476`(基数 1 退化时 p50≈0.048)。
峰值内存 1.31 GB。

## 5. 残留风险(诚实记账)

1. **ACMM 的 MIT 声明本身是否有效,是法律判断不是技术判断。**
   技术证据对它有利:被复制的部分都是不可版权的样板/格式/教科书算法,
   核心表达是独立的。但"2.9% 相同"不自动等于"不是派生作品" —— 最终要律师定。
2. **我们的暴露面现在≈0 行**,与第 1 点的结论无关 —— 这是这次处理的意义。
3. ⚠️ 若将来代价里可能出现 NaN,插入排序与选择排序会分道扬镳,须重新验字节一致性。

## 6. 复现方法

```bash
# 克隆五个仓库
for r in GhiXu/ACMM GhiXu/ACMH GhiXu/ACMP whoiszzj/APD-MVS kysucix/gipuma; do
  git clone --depth 1 https://github.com/$r.git $(basename $r)
done
# 逐行重复块扫描(脚本见 tools/dupscan.py)
python3 tools/dupscan.py ACMM
```
