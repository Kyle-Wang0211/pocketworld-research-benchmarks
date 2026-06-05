# Official DA3 image-only CoreML static export probe

## 结论

`tools/python/export_da3_image_only_coreml.py` 已经可以用 `--static-shape-export-patches` 把官方 image-only DA3 wrapper 导出成 CoreML。这个导出路径只接收 `image`，仍然调用官方 image-only 语义：

`net(image, None, None, export_feat_layers=[], infer_gs=False, use_ray_pose=False, ref_view_strategy="saddle_balanced")`

它不是 AR/identity-camera/外部相机路径。静态补丁只把固定 `B=1,K,H,W` CoreML 资源里的 shape 推导、position embedding、RoPE 坐标、camera decoder reshape 和 intrinsics 构造改成 CoreML converter 能接受的写法。

## 已通过的转换

| Probe | Precision | Status | Output |
|---|---:|---:|---|
| K3 28x28 image-only | float16 | pass | `DA3BASE_static_tiny_K3_28x28_image_only.mlpackage` |
| K3 28x28 image-only | float32 | pass | `DA3BASE_static_tiny_K3_28x28_image_only_fp32.mlpackage` |
| K35 28x28 image-only | float16 | pass | `DA3BASE_static_K35_28x28_image_only.mlpackage` |
| K35 56x56 image-only | float16 | pass | `DA3BASE_static_K35_56x56_image_only.mlpackage` |
| K35 112x112 image-only | float16 | pass | `DA3BASE_static_K35_112x112_image_only.mlpackage` |
| K35 168x280 image-only | float16 | pass | `DA3BASE_static_K35_168x280_image_only.mlpackage` |
| K35 252x392 image-only | float16 | pass | `DA3BASE_static_K35_252x392_image_only.mlpackage` |
| K35 336x532 image-only | float16 | dry-run pass / conversion fail | no package |

K35 252x392 package signature 已验证：

- input: `image [1, 35, 3, 252, 392]`
- outputs:
  - `depth [1, 35, 252, 392]`
  - `depth_conf [1, 35, 252, 392]`
  - `pred_extrinsics [1, 35, 3, 4]`
  - `pred_intrinsics [1, 35, 3, 3]`

没有 `extrinsics` / `intrinsics` 输入。

## Scaling probe

| Probe | Dry-run elapsed | Conversion elapsed | Package size |
|---|---:|---:|---:|
| K35 28x28 | `0.626s` | `35.443s` | `199M` |
| K35 56x56 | `0.934s` | `28.857s` | `210M` |
| K35 112x112 | `2.206s` | `33.657s` | `256M` |
| K35 168x280 | `8.790s` | `72.748s` | `422M` |
| K35 252x392 | `16.426s` | `131.776s` | `673M` |
| K35 336x532 | `38.142s` | fail / abnormal termination | no package |

`252x392` 已经接近目标 `476x742` 的宽高比，并且完整 CoreML conversion pass。这说明当前 blocker 不再是 image-only 语义或 static export patch 的可行性，而是目标分辨率下的 trace/conversion 内存、package size、数值 parity 和设备端性能门槛。

`336x532` dry-run 也通过，输出全 finite；`/usr/bin/time -l` 记录 dry-run peak memory footprint 约 `14.99GB`。同尺寸 conversion 异常退出，没有写出 report/package；`time -l` 记录 conversion peak memory footprint 约 `37.62GB`。因此 `336x532` 以上在本机已经接近 CoreML conversion 资源门槛。

Attention scale reference:

| Resolution | Patch grid | Global tokens | Attention score elems | vs 252x392 |
|---|---:|---:|---:|---:|
| 252x392 | 18x28 | 17,675 | 312,405,625 | 1.00x |
| 336x532 | 24x38 | 31,955 | 1,021,122,025 | 3.27x |
| 476x742 | 34x53 | 63,105 | 3,982,241,025 | 12.75x |

## 数值 smoke test

K3 28x28 float32 CoreML package 对同一随机输入与 PyTorch wrapper 对比：

| Output | Max abs | Mean abs | Max rel |
|---|---:|---:|---:|
| `depth` | `1.4305e-6` | `7.8102e-7` | `1.3796e-6` |
| `depth_conf` | `3.5763e-6` | `1.4901e-6` | `3.2320e-6` |
| `pred_extrinsics` | `7.5027e-6` | `1.4332e-6` | `2.4256e-4` |
| `pred_intrinsics` | `4.0039e-2` | `4.3729e-3` | `5.3401e-4` |

K3 28x28 float16 package 也能 predict，但与 PyTorch float32 有明显误差；这说明后续产品模型需要单独设置 precision/parity gate，不能只看 conversion pass。

## 解决过的 converter blocker

原始 image-only wrapper 的 tiny conversion 失败在 PyTorch frontend `int` op。静态补丁逐步移除了这些 blocker：

- backbone 输入 `einops` reshape 的动态 `int`
- DINO 位置编码的 `upsample_bicubic2d`
- RoPE 坐标和 `int(positions.max())`
- local/global attention 的动态 qkv/head reshape
- image-only camera token 的动态 `S - 1`
- DualDPT head 的动态 shape、UV positional embedding 和 head reshape
- `cam_dec` 的动态 `B*N` reshape
- intrinsics 的 in-place tensor assignment
- `affine_inverse` 里的 unsupported `mT` op

## 仍未关闭

这还不是 APP 可用的正式模型。

- 还没有导出 `DA3BASE_476x742_N35_image_only.mlpackage`；当前最高已通过完整 conversion 的 K35 image-only probe 是 `252x392`，当前最高已通过 dry-run 的 probe 是 `336x532`。
- 还没有把 image-only model 放入 APP bundle 并跑 readiness gate。
- 还没有做 K35 target-resolution CoreML vs PyTorch 数值 parity。
- 还没有做设备端性能、内存、ANE/GPU compute-unit 测试。
- 当前环境 `coremltools 9.0` 警告 `torch 2.12.0` 未在官方测试范围内；生产导出建议复测 `torch 2.7.0` 环境。

## 当前判断

官方 image-only DA3 CoreML 导出在工程上已经可行，中间分辨率 K35 固定窗口已经转换成功到 `252x392`。`336x532` 的失败是本机 CoreML conversion 资源门槛，不是官方 image-only 语义失败。下一步应在更大内存环境或更可控的导出环境里继续推目标 `476x742`，同时保持 APP policy 不回退到 ARKit/外部相机输入。
