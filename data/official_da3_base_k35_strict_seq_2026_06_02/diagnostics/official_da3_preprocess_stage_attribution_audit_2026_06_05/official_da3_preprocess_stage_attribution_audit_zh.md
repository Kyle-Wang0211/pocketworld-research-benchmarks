# Official DA3 preprocess stage attribution audit

- status: `pass_product_preprocess_stage_parity_with_native_kernel`
- dominant observed gap: `None`
- runtime tensor boundary exact: `True`
- source JPEG decode byte-exact: `False`
- source JPEG max abs uint8: `12`
- canonical resize max abs uint8 equiv upper: `1.0177800375223158`

## 大白话

- 产品 official preprocess 主路径已经闭合：source_highres -> C++ OpenCV/libjpeg -> photos_depth/photos_depth_tensor 与官方 Python InputProcessor exact match。
- full_highres_preprocess 当前 max_abs_normalized=0.0，runtime tensor boundary max_abs_normalized=0.0。
- Dart package:image source decode probe 仍然不是 byte-exact，但它现在只是 fallback 风险，不是产品 official preprocess 主路径。
- canonical_source_rgb probe 仍记录 Dart fallback resize/rounding residual，上界约 1.0177800375223158 个 uint8。
- 下一步：产品 official preprocess 已由 C++ OpenCV/libjpeg kernel 闭合；下一步是把 APP 平台包默认接到该 kernel，并继续补 image-only CoreML artifact/signature。

## Rows

| stage | status | key evidence | interpretation |
| --- | --- | --- | --- |
| `source_jpeg_decode` | `warning` | byte_exact=False; max_abs_uint8=12; mean_abs_uint8=0.5644947077041458 | 这是当前最大的输入像素差异源；只修 resize 不能关闭官方 high-res source parity。 |
| `full_highres_preprocess` | `pass` | exact=True; max_abs_norm=0.0; sample_count=32 | 这段边界已经 exact；native/CoreML 不再引入额外 decode 差异。 |
| `canonical_source_resize` | `warning` | exact=False; max_abs_norm=0.017429232597351074; sample_count=1 | JPEG decode 被固定后仍有约 1 个 uint8 级别的 resize/rounding residual；这是小差异但仍不是官方 byte-exact。 |
| `runtime_tensor_boundary` | `pass` | exact=True; max_abs_norm=0.0; sample_count=32 | 这段边界已经 exact；native/CoreML 不再引入额外 decode 差异。 |
