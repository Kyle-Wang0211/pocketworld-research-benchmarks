# KIRI 链成网 + 贴图(2026-09-23 / 24)

同一场景:132 张 4032×3024 照片(`mvs_P16k`),CasDiffMVS **full_ep0** 深度(md5 `e71dc850478eaf937b0f956d92a2814b`)。

## 用户定下的链(09-24)

1. **深度**:官方 `test.py`,参数见 `taiwan_rebuild/infer_arm.sh`(768×576、num_view 10、numdepth 48/384)。
2. **过滤**:官方 `filter.py` 逐视图重放(photo 0.3/0.5/0.5、≥3 视图 / 1 px / 1%)。
   - 自检:有效像素 **36,233,053** = `pc_t3.ply` 点数。
   - 实现:`tsdf_four.py cache`。
3. **TSDF**:照抄 GauStudio `extract_mesh.py`@132d749d(KIRI 上游,MIT),见 `kiri/kiri_tsdf.py`。
   - 参数:VDBFusion `voxel_size=0.01, sdf_trunc=0.04, space_carving=False`,`extract_triangle_mesh(min_weight=5)`。
   - 结果:**2,071,895 顶点 / 3,781,890 三角**。
4. **贴图**:texrecon,用 GauStudio README 原参数 `--outlier_removal=gauss_clamping --data_term=area --no_intermediate_results`。
   - 用**官方默认**:没被任何照片看到的面删掉,用户 09-24 拍板。见 `tex/run_tex.sh`。
   - 结果:输出 **3,371,867 三角**、217 张图集;440,107 个面没被看到,其中 30,084 个由 texrecon 自带补洞补上,410,023 个(10.8%)被删。
   - 资源:91 s,峰值内存 19.6 GB。

## 对照臂(均已判,留作记录)

尺子相同(修正版双层率 layer2F / 三角尺寸 / 流形)。

| 臂 | 三角 | 双层率 | 备注 |
|---|---|---|---|
| A 现状(Open3D TSDF 3mm + 去碎 + Taubin) | 85.6M | 19.2% | 面积 235 m² |
| **KIRI 1cm(选定)** | 3.78M | 18.1% | 面积 120,回路 32,827,边长 12.8 mm |
| KIRI 3mm | — | — | 碎成 42.5 万块,面积 61 |
| KIRI 5mm 门槛 5 | — | 13.4% | 面积 81,回路 6.9 万 |
| KIRI 5mm 门槛 1.25 | — | 16.8% | 面积 126,碎成 29.8 万块 |
| VGGT-1B-Commercial 深度 → KIRI 1cm | — | 27.1% | 置信度≥5 只留 39%,相机对齐残差 64 mm |
| MapAnything-apache 吃我们位姿 → KIRI 1cm | — | 48.2% | 输出位姿被重估(34 mm) |

- **四点融合改动**(`tsdf_four.py run`:取整 / voxblox 衰减 / 1/z² / MVE 边界置信):用户判「全面的删减」,已判死。
- 为什么小体素反而覆盖小:VDBFusion 权重按射线计;每体素每视图射线数约 (体素/像素足迹)²,1cm≈21、5mm≈5.4、3mm≈1.9;marching cubes 要求 8 个角都 ≥ 门槛。
- **VGGT 原样全部点**(`vggt/vggt_official_demo.py`):官方 `demo_gradio.run_model()` 逐字 + `predictions_to_glb(conf_thres=0)`。
  - 132×392×518 = 26,803,392 点(每像素一个)。
  - 22.5 s,显存 16.2 GB。
- 贴图「保留未见面」臂(`tex/run_keep.sh`,texrecon 官方 `--keep_unseen_faces`)跑过对照,用户选了默认(删)。

## 重建(旧箱 09-24 离线后)

`taiwan_rebuild/` 是在另一台机器上按原脚本重跑的版本,只换了解释器路径与 GPU 编号。验收标准是上面的计数逐个对上。

大文件不入库,见 `MANIFEST.md`。
