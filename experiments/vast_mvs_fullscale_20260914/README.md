# vast_mvs_fullscale_20260914 — CasDiffMVS 全域全量训练线(旧机 ssh7:15937 归档)

旧机 2026-09-14 销毁前的全部实验脚本/日志/清单快照。数据本体(~2.3 TB)已 md5 对账搬到新机
(m:36004 Texas, 6.5 TB)。脚本一律**整本复刻一家权威源**,出处写在各文件头部。

## 线索
- `scripts/train_AB.sh` 快档 A+B(SimpleProc 983 场景 33% + TA 室内/TG 67%, 21,466 元组, 16 epochs)
  → 用户肉眼判决: ep2 最好, ep6 回潮, **ep15 最烂** ⇒ 病根 = 数据量(每样本被喂 16 遍)
- `scripts/train_full.sh` 全域全量版: 六域(SimpleProc 44,000 / BlendedMVG / TartanAir / TartanGround / GSO / ARKitScenes)
  **每数据集等量采样**(DUSt3R arXiv 2312.14132 §4), `--domain_balance 100000` ⇒ 60 万/epoch × 16 = 9.6M
  (= SimpleProc 官方 max_steps 1.6M × batch 6)
- `scripts/domain_sampler.py` + `scripts/train_py_domain_balance.patch`(官方 train.py 11 行补丁, CRLF 保留)
- `scripts/test_domain_sampler.py` 四项验证 / `scripts/smoke_loader.py` 开训前冒烟 / `scripts/build_full_lists_v2.py`
- 转换器: `sp2mvsnet.py`(SimpleProc) / `tartanair_to_blend.py` / `tartanground2mvsnet.py` / `arkit2blend.py`(ARKitScenes, 出处见文件头)
  / `gso_stage1.py`+`gso_stage2.py`(GSO 渲染 1024×768 → 768×576)
- 流式下载: `sp_fetch_par.py`+`sp_stream.sh` / `arkit_stream.sh`+`arkit_all.sh`
- 推理/融合/判决: `infer_arm.sh`(ETH3D 档融合常数, VAR_GATE=TEX_GATE=0) / `fuse_only.py` / `quick_arm.sh` / `ply2bins.py` / `gen_meta.py`
- 搬运: `migrate_real.sh` / `migrate_rest.sh` / `archive_rest.sh`(rsync + 逐文件 md5; 🔴 `tar|tar` 会静默损坏, 不用)
- 已否决(留档): `plane_fit.py`(d_max 1cm vs 层间距 0.03-0.45m) / `layer_sweep.py`(ref-ref 分歧不敏感) / 方差门

## 分辨率
训练/渲染/推理统一 768×576(CasDiffMVS 官方 BlendedMVS 低清口径, blend.py 不 resize)。
