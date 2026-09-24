# DA3-BASE K35 标准实验包

## 标准范围

这份目录是当前 DA3-BASE / K35 / 476x742 路线的标准实验包。远端保留的内容应该覆盖：

- strict no-loop CoreML 基线输出、数值、图片和 window 诊断。
- official-filter no-loop CoreML micro audit 输出、数值和图片。
- official PyTorch 同分辨率小 K reference sweep 输出、数值和运行报告。
- official streaming mobile constrained config：`chunk_size=35`、`overlap=18`、`loop_enable=True`，其余尽量保持官方默认。
- 复现实验用脚本与环境指纹。

## 当前边界

- 本地 MPS 已跑通官方 PyTorch reference 的小 K：476 下 K=3/5/10，742 下 K=3/5。
- 本地 MPS 未跑通完整 K35@476/742：476 在 K35 触发 15.36 GiB MPS buffer；742 在 K10 附近触发约 15.6 GB private buffer 原生 abort，完整 K35@742 预计远超本机内存。
- K=1/2 的失败发生在官方 Umeyama pose alignment 阶段，原因是帧数过少导致退化，不代表单帧 depth forward 失败。
- 当前没有加入自研 graph patch、loop fusion 或新算法；后续 loop-enabled 对齐应只走官方 loop / Sim3 / VPR 路径。

## 本地清理原则

本地历史环境和历史实验目录可以清理，但前提是：

1. 这份标准包已经 commit 并 push 到远端。
2. Git LFS 对 `.npy`、`.ply`、`.png` 等大文件已生效。
3. 远端能看到算法脚本、config、实验数据、图片、报告和环境指纹。
4. 清理只针对旧路线或非标准中间产物，不删除仍作为当前标准包输入/输出的目录。

不建议直接把完整 Python venv 提交到 git。标准做法是提交官方源码 commit、官方 requirements 来源、实际运行关键依赖版本、模型权重 SHA256、运行命令和结果报告。
