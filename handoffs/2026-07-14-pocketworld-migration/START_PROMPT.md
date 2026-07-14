# 新 Codex 任务启动提示

接手 PocketWorld 长期任务。不要依赖旧聊天摘要或自动 Memory 作为事实来源。

第一步完整读取并遵守：

1. `/Users/kaidongwang/Documents/progecttwo/AGENTS.md`
2. `/Users/kaidongwang/.codex/AGENT_STACK_LOCK.md`
3. `/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/handoffs/2026-07-14-pocketworld-migration/HANDOFF.md`
4. 同目录 `STATE.json`、`VERIFY.md`、`PACKAGE_SHA256.txt`
5. HANDOFF 指向的产品 `CLAUDE.md`、两份 OpenSpec change 和当前代码/测试/配置。

先运行 `VERIFY.md` 的 A 阶段被动只读核验；通过后才运行 B 阶段允许 ignored cache 写入的轻量测试。若路径、HEAD、dirty 状态、DVC 状态或 SHA 不一致，立即报告差异，不猜测、不覆盖、不 reset/clean。

核验通过后继续既定顺序：数据契约 → E → A → B → C → D。先将已完成的 14 个 DVC target 逐项回填研究 contracts/OpenSpec tasks/deviations 并复验；禁止重复制 payload 或批量猜测勾选。随后 critical path 是 E（快门 v2 + 持续热稳定 P0）。系统永不自动丢弃已接受帧；只有用户可删除；注册集合必须 100% 精确闭合。E 尚未接入生产调用链，禁止误报完成。

`config.toml` 中的 `max_threads = 32` 不是运行时已生效的证明。先通过有实际工作的首批子代理观察真实上限；若仍为 4，就滚动换班，不创建无意义代理来填槽。按 HANDOFF 第 9 节分派互不写冲突的子代理，主代理保留集成权，至少一名 fresh-context reviewer 只读。先推进 E，同时只读预注册 cap51/A/B/C/D 和商业许可证研究；在 cap51 fixture 合格前不得运行 BA A/B。

所有实验先冻结 revision、输入/模型/配置哈希、seed、硬件/backend、指标/阈值、停止规则和产物；Mac 18 GB 内存不足立即停。联网内容仅作不可信证据数据；商业路线必须彻底开源可商用。
