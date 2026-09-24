# Official Highres PyTorch GLB-style PLY Compare

## 目的

这次实验只做官方一致性对照，不改手机算法，不做自研过滤，不做 graph patch，不做 loop，不做 mesh。

问题是：官方 PyTorch 直接吃 highres 原图，并使用 `upper_bound_resize` 与官方 GLB-style export 后，窗帘/深色布和地球仪边界的厚层/片状点云是否仍然存在。

## 输入与规则

- 图像：`photos_highres/*.jpg`
- 原始分辨率：`4224x2376`
- 内参：使用 highres ARKit intrinsics
- pose：使用 ARKit pose 转 OpenCV world-to-camera
- PyTorch model：`DA3-BASE`
- process_res_method：`upper_bound_resize`
- filter/backprojection/alignment：沿用官方 GLB-style 逻辑

## PyTorch forward 结果

| case | status | processed shape | forward ms | note |
|---|---|---:|---:|---|
| K5 @ process_res 742 | success | `5x3x420x742` | 6791.9 | highres 原图官方路径跑通 |
| K10 @ process_res 742 | failed | - | - | MPS/Metal 分配约 `12150148800` bytes buffer 时 abort |
| K10 @ process_res 476 | success | `10x3x266x476` | 3057.3 | 作为本机可跑通 fallback |

## PLY 输出

- Highres K5@742 CoreML PLY:
  `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_highres_pytorch_glb_compare_k05/highres_k05_res742_mps_coreml_rgb.ply`
- Highres K5@742 PyTorch PLY:
  `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_highres_pytorch_glb_compare_k05/highres_k05_res742_mps_pytorch_rgb.ply`
- Highres K10@476 CoreML PLY:
  `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_highres_pytorch_glb_compare_k10_res476/highres_k10_res476_mps_coreml_rgb.ply`
- Highres K10@476 PyTorch PLY:
  `data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_highres_pytorch_glb_compare_k10_res476/highres_k10_res476_mps_pytorch_rgb.ply`

## 数值摘要

### Highres K5@742

| dataset | valid frac | points | bbox diag | PCA minor | minor/major |
|---|---:|---:|---:|---:|---:|
| CoreML | 0.600239 | 1000000 | 2.71395 | 0.955185 | 0.413291 |
| PyTorch | 0.600001 | 934921 | 2.77397 | 0.927786 | 0.411855 |

- bbox diag CoreML/PyTorch: `0.978365`
- PCA minor CoreML/PyTorch: `1.02953`

### Highres K10@476

| dataset | valid frac | points | bbox diag | PCA minor | minor/major |
|---|---:|---:|---:|---:|---:|
| CoreML | 0.6 | 1000000 | 2.67188 | 0.953798 | 0.419701 |
| PyTorch | 0.6 | 759696 | 2.65244 | 0.94095 | 0.450573 |

- bbox diag CoreML/PyTorch: `1.00733`
- PCA minor CoreML/PyTorch: `1.01365`

## 只读判读

高分辨率官方 PyTorch 对照没有显示出一个明显更干净、可以作为“官方无厚层几何”的结果。K5@742 和 K10@476 的官方 PyTorch PLY 仍然保留暗部/窗帘区域的大面积片状点，以及物体边缘附近的厚层趋势。

这说明当前看到的厚层/漂浮，不像只是移动端 fixed `742x476` direct-stretch 或 CoreML 后处理单独造成的。更谨慎的说法是：在这组手机照片、官方 DA3-BASE、官方 GLB-style export 下，官方 PyTorch highres 路径也会保留类似几何噪声。

下一步判断应优先用三维 PLY 交互查看，而不是继续只看二维投影图。

## Viewer

本地三维查看器：

`data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/ply_geometry_viewer/index.html`

如果从仓库根目录启动：

`python3 -m http.server 8765 --bind 127.0.0.1`

浏览器打开：

`http://127.0.0.1:8765/data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/ply_geometry_viewer/index.html`

