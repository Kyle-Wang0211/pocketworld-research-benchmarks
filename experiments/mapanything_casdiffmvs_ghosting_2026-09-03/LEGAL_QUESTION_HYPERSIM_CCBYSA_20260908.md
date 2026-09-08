# 法务咨询：能否用 Hypersim（CC BY-SA 3.0）训练我们要商用出货的模型

**日期**：2026-09-08　**提出人**：重建算法线　**性质**：请法务判定，不是技术方案

> 本文只陈述事实和问题，**不含任何法律结论**。技术侧不具备法律判断资格。

---

## 一、我们为什么要问

我们的三维重建引擎在**大面积无纹理白墙**上有结构性缺陷（墙面把前景物体"粘"过去）。
今天已用实验证明：这不是物理定律——同样 132 张照片、同样相机位姿、同样融合判据，
换成一个**训练数据里包含真实室内白墙场景**的模型（MVSAnywhere），缺陷基本消失。

我们已排查全部候选训练数据的许可，结论是：

- **带真值几何的"真实"室内数据集几乎全部禁止商用**（ScanNet++、ScanNet、ARKitScenes、
  Matterport3D、Structured3D、3D-FRONT、HSSD、Taskonomy…），原因大概率是它们扫描的是私人住宅。
- 允许商用的室内数据只剩**合成**的，其中最对症的是 **Hypersim**。

所以 Hypersim 能不能用，直接决定这条技术路线走不走得通。

---

## 二、事实（全部核到原始文件）

### 2.1 数据集与许可

- 名称：**Hypersim**，Apple 发布，ICCV 2021
- 仓库：https://github.com/apple/ml-hypersim
- 许可原文（README 逐字）：
  > "The Hypersim Dataset is licensed under the **Creative Commons Attribution-ShareAlike 3.0 Unported License**"
- 许可全文：https://creativecommons.org/licenses/by-sa/3.0/legalcode
- ⚠️ 注意：仓库里的 `LICENSE.txt` 是 **Apple 的代码许可**，与上面这条**数据**许可是两件事。

### 2.2 数据集内容

- 461 个室内场景，公开发布 **74,619 张**图（原 77,400，剔除了含人物和显著 logo 的）
- 含：逐像素**深度真值**、相机参数、语义标注、光照分解
- **不含三角网格**。README 明确：要拿网格必须自行到 TurboSquid 购买 Evermotion 素材
  （Archinteriors Vol. 1–55，除 20/25/40/49）
- 🔑 **我们只需要"图像 + 深度真值"，这两项都在 CC BY-SA 的公开发布范围内，不需要买 Evermotion。**

### 2.3 我们打算做什么 / 不做什么

**会做：**
1. 下载 Hypersim 公开发布的图像与深度真值
2. 转换成我们训练框架的输入格式（不改变内容，只改文件组织）
3. 用它**训练/微调**一个多视图立体深度估计网络
4. 把**训练出来的权重**打包进我们的 **toC 手机 App**，随 App 分发（商业产品）

**不会做：**
- 不转售、不再分发 Hypersim 的图像或深度数据本身
- 不把 Hypersim 的任何原始文件放进 App 或服务器公开访问
- 模型不生成 Hypersim 的图像，输出是**用户自己拍摄照片**重建出的三维几何

---

## 三、请法务回答的问题

1. **核心问题**：用 CC BY-SA 3.0 的数据训练神经网络，产出的**模型权重**是否构成该许可下的
   **Adaptation（演绎作品）**，从而触发 ShareAlike——即必须以同一许可（CC BY-SA 3.0）发布权重？

2. 如果构成 Adaptation：我们把权重**编译进 App 二进制随产品分发**，是否算许可意义上的
   "publicly share / distribute"？（这决定 ShareAlike 义务是否被触发）

3. 如果 ShareAlike 被触发，实际后果是什么？是必须**公开权重**，还是仅需在权重的分发上附加
   CC BY-SA 条款？这对我们的商业模式是否可接受？

4. **署名义务（BY）**：无论 SA 是否触发，我们是否需要在 App 内（如"关于/开源许可"页）
   署名 Hypersim / Apple？如需要，标准写法是什么？

5. **管辖与版本**：CC BY-SA **3.0 Unported**（非 4.0）在我们目标市场（中国、美国、欧盟）
   的适用与差异，是否有需要特别注意的地方？

6. **风险容忍度**：若此问题在法律上确无定论（见下节），公司愿意承担这个不确定性，
   还是要求走**零争议**的替代路径？

---

## 四、已经查到的公开材料（供法务参考，非结论）

### 4.1 Creative Commons 官方指引

《[Using CC-Licensed Works for AI Training](https://creativecommons.org/using-cc-licensed-works-for-ai-training-2/)》
（[PDF](https://creativecommons.org/wp-content/uploads/2025/05/Using-CC-licensed-Works-for-AI-Training.pdf)）
两处与本问题直接相关：

- BY / SA / ND 条件**只在作品或其演绎被公开分享时才被触发**
- 若 AI 模型或其输出**基于 ShareAlike 内容且将被公开分享**，遵守 SA 就要求开发者
  以同一 CC 许可发布

### 4.2 学术讨论

Szkalej & Senftleben，《Generative AI and Creative Commons Licences: The Application of
Share Alike Obligations to Trained Models, Curated Datasets and AI Output》
（[SSRN 4872366](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4872366) /
[JIPITEC](https://www.jipitec.eu/jipitec/article/view/415)）——主题与本问题完全重合。

### 4.3 现状

据我们所查，**"模型权重是否为训练数据的演绎作品"目前没有确定判例**。
这正是需要法务判断风险敞口的地方。

---

## 五、若答案是"不能用"，我们有干净的替代（无需法务再判）

**Infinigen / Infinigen Indoors**（Princeton，CVPR 2024）
- 仓库：https://github.com/princeton-vl/infinigen
- 许可：**BSD 3-Clause**（LICENSE 首行逐字："BSD 3-Clause License / Copyright (c) 2023, Princeton University"）
- 性质：**程序化生成器**，不是数据集——我们自己生成室内场景与真值，数量不限
- 第三方素材：Poly Haven，**CC0**（任何用途含商用，无需署名）
- 依赖 Blender（GPL），但 GPL 不覆盖程序**输出**
- 代价：要先搭生成管线；且社区评价它"高保真但**计算开销大**"

**技术侧对两条路的判断是等价的**：Hypersim 是现成的、Infinigen 是干净的。
**选哪条完全取决于法务对第三节的回答。**

---

## 六、法务回答之前，技术侧照常推进的部分

以下工作与数据集选择无关，不等法务：

1. 数据 → 训练格式的转换器（两个数据集共用同一套输出格式）
2. 🔴 Hypersim 的已知技术坑（与许可无关，但会毁掉训练）：
   `depth_meters` 存的是**到相机中心的射线距离，不是平面深度 Z**
   （Apple 仓库 [issue #9](https://github.com/apple/ml-hypersim/issues/9) 标题即为
   "ground truth depth is actually distance"），且相机位置以 asset units 存储
3. 评测链路：同 132 张 / 同官方融合门 / 同并排页，已就绪
