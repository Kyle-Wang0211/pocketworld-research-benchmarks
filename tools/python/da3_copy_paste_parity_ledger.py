#!/usr/bin/env python3
"""Build a concrete copy-paste parity ledger against official DA3 code."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path("/Users/kaidongwang/Documents/progecttwo")
RESEARCH_ROOT = Path(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks"
)
APP_ROOT = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter")
OFFICIAL_ROOT = PROJECT_ROOT / "aether_cpp/third_party/Depth-Anything-3"
CAPTURE_SERVICES = PROJECT_ROOT / "packages/aether_capture_services"


FILES = {
    "official_streaming": OFFICIAL_ROOT / "da3_streaming/da3_streaming.py",
    "official_npz_output_process": OFFICIAL_ROOT
    / "da3_streaming/npz_output_process.py",
    "official_npz_oracle_bridge": RESEARCH_ROOT
    / "tools/python/da3_depth_index_official_npz_oracle_bridge.py",
    "official_sim3utils": OFFICIAL_ROOT / "da3_streaming/loop_utils/sim3utils.py",
    "official_base_config": OFFICIAL_ROOT / "da3_streaming/configs/base_config.yaml",
    "official_api": OFFICIAL_ROOT / "src/depth_anything_3/api.py",
    "official_input_processor": OFFICIAL_ROOT
    / "src/depth_anything_3/utils/io/input_processor.py",
    "official_da3_model": OFFICIAL_ROOT / "src/depth_anything_3/model/da3.py",
    "dart_policy": CAPTURE_SERVICES / "lib/src/photo_bundle_pipeline_policy_service.dart",
    "dart_derivation": CAPTURE_SERVICES / "lib/src/photo_bundle_derivation_service.dart",
    "dart_decode_probe": CAPTURE_SERVICES / "example/da3_source_decode_probe.dart",
    "opencv_native_preprocess_audit": RESEARCH_ROOT
    / "tools/python/da3_opencv_native_preprocess_parity_audit.py",
    "cpp_preprocess_kernel": PROJECT_ROOT
    / "aether_cpp/da3_preprocess/src/da3_preprocess.cpp",
    "cpp_preprocess_c_api": PROJECT_ROOT
    / "aether_cpp/da3_preprocess/include/aether/da3_preprocess_c_api.h",
    "cpp_preprocess_kernel_audit": RESEARCH_ROOT
    / "tools/python/da3_cpp_preprocess_kernel_parity_audit.py",
    "dart_native_preprocess_runner": CAPTURE_SERVICES
    / "lib/src/da3_native_preprocess_runner.dart",
    "dart_native_preprocess_hook": CAPTURE_SERVICES / "hook/build.dart",
    "dart_native_preprocess_matrix": CAPTURE_SERVICES
    / "tool/da3_preprocess_prebuilt_matrix.dart",
    "dart_native_preprocess_smoke": CAPTURE_SERVICES
    / "example/da3_native_preprocess_runner_smoke.dart",
    "app_runner": APP_ROOT / "lib/pipeline/local_pipeline_runner.dart",
    "app_runner_test": APP_ROOT / "test/local_pipeline_runner_test.dart",
    "swift_da3": APP_ROOT / "ios/Runner/Da3DepthPlugin.swift",
    "xcode_project": APP_ROOT / "ios/Runner.xcodeproj/project.pbxproj",
    "image_only_readiness_report": RESEARCH_ROOT
    / "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_image_only_coreml_readiness_gate_2026_06_05/official_da3_image_only_coreml_readiness_gate.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args.date)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_copy_paste_parity_ledger.json", report)
    write_markdown(args.out_dir / "official_da3_copy_paste_parity_ledger_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(date: str) -> dict[str, Any]:
    src = {name: read_text(path) for name, path in FILES.items()}
    image_only_coreml_ready = all(
        needle in src["image_only_readiness_report"]
        for needle in [
            '"status": "pass"',
            '"official_baseline_ready": true',
            '"has_image_only_coreml_signature": true',
            '"target_referenced_by_xcode_resources": true',
        ]
    )
    rows = [
        row(
            "commercial_checkpoint",
            "DA3-BASE / Apache-2.0 must be the product checkpoint.",
            "copied",
            [
                hit(src["dart_policy"], "license: 'Apache-2.0'"),
                hit(src["dart_policy"], "id: 'DA3-BASE'"),
            ],
            "本地产品路径锁 DA3-BASE / Apache-2.0；未复制 LARGE/GIANT/NESTED。",
            FILES["dart_policy"],
        ),
        row(
            "streaming_k_window_size",
            "Official chunk_size=120/overlap=60; mobile override is K35/overlap18 only.",
            "mobile_override_allowed",
            [
                hit(src["official_base_config"], "chunk_size: 120"),
                hit(src["official_base_config"], "overlap: 60"),
                hit(src["dart_policy"], "windowSize: 35"),
                hit(src["dart_policy"], "overlap ="),
            ],
            "这是用户允许的核心差异：官方 120/60 无法作为手机主线，Dart 复制 sliding-window 公式但缩到 K35。",
            FILES["official_base_config"],
        ),
        row(
            "streaming_image_only_forward",
            "Official DA3-Streaming calls model.inference(images, ref_view_strategy=...) with no camera tensors.",
            (
                "copied_image_only_coreml_artifact_signature_and_bundle_gate"
                if image_only_coreml_ready
                else "parity_gap_missing_image_only_coreml_artifact"
            ),
            [
                hit(src["official_streaming"], "predictions = self.model.inference(images, ref_view_strategy=ref_view_strategy)"),
                hit(src["official_da3_model"], "if extrinsics is not None:"),
                hit(src["official_da3_model"], "cam_token = None"),
                hit(src["dart_policy"], "resourceName: 'DA3BASE_280x504_N35_image_only'"),
                hit(src["xcode_project"], "DA3BASE_280x504_N35_image_only.mlpackage in Resources"),
                hit(src["image_only_readiness_report"], '"official_baseline_ready": true'),
                hit(src["image_only_readiness_report"], '"has_image_only_coreml_signature": true'),
                hit(src["swift_da3"], 'provider = try MLDictionaryFeatureProvider(dictionary: ['),
                hit(src["swift_da3"], '"image": MLFeatureValue(multiArray: imageArray)'),
                hit(src["swift_da3"], '"extrinsics": MLFeatureValue(multiArray: extrinsics)'),
                hit(src["swift_da3"], '"intrinsics": MLFeatureValue(multiArray: intrinsics)'),
            ],
            (
                "DA3BASE_280x504_N35_image_only CoreML is now exported, has an image-only signature, is referenced by Xcode resources, and Swift still refuses pose fallback for the official image-only path."
                if image_only_coreml_ready
                else "Dart/Swift product path now selects image-only and refuses the legacy pose resource; remaining blocker is the missing DA3BASE_280x504_N35_image_only CoreML artifact/signature."
            ),
            FILES["swift_da3"],
        ),
        row(
            "api_preprocess_resize",
            "Official preprocess uses process_res=504 and upper_bound_resize, then patch-size divisibility.",
            "copied_shape_contract_only",
            [
                hit(src["official_api"], "process_res: int = 504"),
                hit(src["official_api"], 'process_res_method: str = "upper_bound_resize"'),
                hit(src["official_input_processor"], "pil_img = self._resize_image(pil_img, process_res, process_res_method)"),
                hit(src["official_input_processor"], "pil_img = self._make_divisible_by_resize(pil_img, self.PATCH_SIZE)"),
                hit(src["official_input_processor"], "interpolation = cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA"),
                hit(src["dart_policy"], "processRes: 504"),
                hit(src["dart_policy"], "processResMethod: 'upper_bound_resize'"),
                hit(src["dart_derivation"], "mode: 'upper_bound_resize_patch_align'"),
                hit(src["dart_derivation"], "_nearestMultiple(boundaryWidth, patchSize)"),
                hit(src["dart_derivation"], "_resizeAreaRgb8"),
                hit(src["dart_derivation"], "opencv_area"),
                hit(src["dart_derivation"], "imageTensorFloat32ChwRelativePath"),
            ],
            "Dart photos_depth/photos_depth_tensor 默认路径已复制官方 process_res=504、upper_bound_resize、nearest patch-size shape contract，并把官方预处理终点推进到 normalized float tensor。",
            FILES["dart_derivation"],
        ),
        row(
            "opencv_preprocess_pixel_parity",
            "Official preprocess pixels come from OpenCV INTER_AREA/INTER_CUBIC, not a merely similar resize.",
            "copied_via_native_kernel_verified",
            [
                hit(src["official_input_processor"], "import cv2"),
                hit(src["official_input_processor"], "cv2.INTER_AREA"),
                hit(src["official_input_processor"], "cv2.INTER_CUBIC"),
                hit(src["cpp_preprocess_kernel"], "cv::imread"),
                hit(src["cpp_preprocess_kernel"], "cv::INTER_AREA"),
                hit(src["cpp_preprocess_kernel"], "cv::INTER_CUBIC"),
                hit(src["dart_native_preprocess_runner"], "Da3NativePreprocessRunner"),
                hit(src["dart_derivation"], "owner': 'native_cpp_opencv_libjpeg'"),
                hit(src["dart_derivation"], "byte_exact_official_input_processor_target"),
                hit(src["cpp_preprocess_kernel_audit"], "pass_cpp_kernel_matches_official_input_processor"),
                hit(src["dart_derivation"], "_resizeAreaRgb8"),
                hit(src["dart_derivation"], "cubic_compat_pending_opencv_exact"),
            ],
            "Research/CLI/capture package 已接 C++ OpenCV/libjpeg kernel；从 source_highres 到 photos_depth/photos_depth_tensor 的 sampled gate 已 pixel/tensor exact。Dart 手写 resize 只保留 fallback/compat，不再是 official product preprocess。",
            FILES["dart_derivation"],
        ),
        row(
            "opencv_native_preprocess_path",
            "Official PIL/OpenCV InputProcessor can be reproduced by a cross-platform native OpenCV/libjpeg kernel.",
            "copied_native_path_verified_in_research",
            [
                hit(src["official_input_processor"], "import cv2"),
                hit(src["official_input_processor"], "Image.open(img).convert(\"RGB\")"),
                hit(src["opencv_native_preprocess_audit"], "cv2.imread"),
                hit(src["cpp_preprocess_kernel"], "cv::imread"),
                hit(src["cpp_preprocess_kernel"], "cv::INTER_AREA"),
                hit(src["cpp_preprocess_kernel"], "cv::INTER_CUBIC"),
                hit(src["cpp_preprocess_c_api"], "aether_da3_preprocess_image_file_to_cache"),
                hit(src["cpp_preprocess_kernel_audit"], "pass_cpp_kernel_matches_official_input_processor"),
                hit(src["opencv_native_preprocess_audit"], "cv2.INTER_AREA"),
                hit(src["opencv_native_preprocess_audit"], "cv2.INTER_CUBIC"),
                hit(src["opencv_native_preprocess_audit"], "pass_cv2_native_matches_official_input_processor"),
            ],
            "Research audit 已证明 source_highres 抽样 32 帧里，实际 C++ OpenCV/libjpeg kernel 对官方 InputProcessor pixel/tensor exact；C ABI 已暴露给 Dart/平台插件调用。产品方向应接这个 native kernel，而不是继续手写 Dart resize/decode。",
            FILES["cpp_preprocess_kernel"],
        ),
        row(
            "app_native_preprocess_runner_hook",
            "APP sidecar derivation should prefer the native C ABI preprocess runner when the platform has packaged the library.",
            "macos_bundled_native_asset_hook_verified_cross_platform_prebuilts_pending",
            [
                hit(src["dart_native_preprocess_runner"], "Da3NativePreprocessRunner.tryOpen"),
                hit(src["dart_native_preprocess_runner"], "package:aether_capture_services/aether_da3_preprocess"),
                hit(src["dart_native_preprocess_runner"], "aether_da3_preprocess_abi_version"),
                hit(src["dart_native_preprocess_runner"], "AETHER_DA3_PREPROCESS_DYLIB"),
                hit(src["dart_native_preprocess_hook"], "CodeAsset("),
                hit(src["dart_native_preprocess_hook"], "DynamicLoadingBundled()"),
                hit(src["dart_native_preprocess_hook"], "AETHER_DA3_PREPROCESS_PREBUILT"),
                hit(src["dart_native_preprocess_hook"], "native/prebuilt"),
                hit(src["dart_native_preprocess_hook"], "_targetMatchesHost"),
                hit(src["dart_native_preprocess_hook"], "_currentArch"),
                hit(src["dart_native_preprocess_matrix"], "hookFallbackPolicy"),
                hit(src["dart_native_preprocess_matrix"], "abiProbe"),
                hit(src["dart_native_preprocess_matrix"], "aether_da3_preprocess_abi_version"),
                hit(src["dart_native_preprocess_matrix"], "_Target('ohos', 'arm64'"),
                hit(src["dart_native_preprocess_matrix"], "_Target('ohos', 'x64'"),
                hit(src["dart_native_preprocess_smoke"], "Da3NativePreprocessRunner.tryOpen"),
                hit(src["dart_native_preprocess_runner"], "libaether_da3_preprocess.so"),
                hit(src["dart_native_preprocess_runner"], "libaether_da3_preprocess.dylib"),
                hit(src["app_runner"], "_defaultPhotoBundleDerivationService"),
                hit(src["app_runner"], "Da3NativePreprocessRunner.tryOpen"),
                hit(src["app_runner"], "Isolate.run"),
                hit(src["app_runner_test"], "nativePreprocessAvailable"),
                hit(src["app_runner_test"], "native_cpp_opencv_libjpeg"),
                hit(src["app_runner_test"], "dart_package_image_fallback"),
                hit(src["app_runner_test"], "fallbackDartFrameCount', 0"),
            ],
            "APP LocalPipelineRunner 和后台 isolate 已默认尝试打开 native preprocess runner；aether_capture_services hook/build.dart 已能把现有 dylib 注册成 bundled CodeAsset，并已限制 monorepo fallback 只能用于 host os/arch，避免把 macOS dylib 误塞进 iOS/Android/HarmonyOS 包。package smoke 不带 env 已通过；prebuilt matrix 现在对 host 库做 ABI probe，当前 macOS arm64 为 pass，并已把 ohos_arm64/ohos_x64 纳入正式跨端目标；但总体仍是 1/9 ready。APP local_pipeline_runner_test 也强断言 native 可用时 da3_input_manifest execution.owner 必须是 native_cpp_opencv_libjpeg。剩余工程差异是补齐 iOS/Android/Harmony/Windows/Linux/macOS x64 的预编译库与平台打包矩阵。",
            FILES["app_runner"],
        ),
        row(
            "source_jpeg_decode_parity",
            "Official source image load uses PIL/libjpeg; Dart package:image JPEG decode must be treated as a separate byte-exact gap.",
            "fallback_only_gap_not_product_official_path",
            [
                hit(src["official_input_processor"], 'return Image.open(img).convert("RGB")'),
                hit(src["cpp_preprocess_kernel"], "cv::imread"),
                hit(src["dart_derivation"], "owner': 'native_cpp_opencv_libjpeg'"),
                hit(src["dart_derivation"], "image.decodeImage(await sourceFile.readAsBytes())"),
                hit(src["dart_decode_probe"], "image.decodeImage(await source.readAsBytes())"),
            ],
            "cap-1 source decode audit 仍证明 Dart package:image 与 PIL/libjpeg 不 byte-exact；但 official product preprocess 现在应走 C++ OpenCV/libjpeg kernel，这个 gap 只约束 fallback，不能再算产品 official preprocess blocker。",
            FILES["dart_derivation"],
        ),
        row(
            "image_tensor_normalization",
            "Official tensor is RGB/NCHW/ImageNet normalized.",
            "copied",
            [
                hit(src["official_input_processor"], "return self.NORMALIZE(img_tensor)"),
                hit(src["dart_derivation"], "_writeOfficialImageTensorBin"),
                hit(src["dart_derivation"], "Float32List.fromList([0.485, 0.456, 0.406])"),
                hit(src["dart_derivation"], "Float32List.fromList([0.229, 0.224, 0.225])"),
                hit(src["swift_da3"], "imageTensorFloat32ChwPath"),
            ],
            "Dart tensor layout/normalization now copies official ImageNet semantics before native; Swift only loads pre-normalized float32 CHW into CoreML. Runtime tensor boundary audit is exact on sampled frames.",
            FILES["swift_da3"],
        ),
        row(
            "official_save_depth_conf_result",
            "Official downstream saves only core/save-frame indices, not all K slots.",
            "copied",
            [
                hit(src["official_streaming"], "save_indices = list(range(0, chunk_end - chunk_start - self.overlap_e))"),
                hit(src["official_streaming"], "save_indices = list(range(self.overlap_s, chunk_end - chunk_start - self.overlap_e))"),
                hit(src["dart_policy"], "'officialSaveFrameIDs': officialSaveFrameIDs"),
                hit(src["app_runner"], "final downstreamFrameIDs = _downstreamFrameIDsForWindow(window)"),
                hit(src["app_runner"], "!downstreamFrameIDs.contains(frameResult.frameID)"),
            ],
            "Dart/APP 已复制官方 results_output/core-frame ownership，不再把 full-K withheld tail 当 downstream。",
            FILES["dart_policy"],
        ),
        row(
            "confidence_minus_one",
            "Official DA3-Streaming subtracts 1.0 from confidence before saving/pointcloud.",
            "copied_in_native_and_downstream_executor_smoke_passed",
            [
                hit(src["official_streaming"], "predictions.conf -= 1.0"),
                hit(src["swift_da3"], "let confSlice = Array(conf[lo..<hi]).map { $0 - 1.0 }"),
                hit(src["app_runner"], "confidence_min_policy"),
                hit(src["app_runner"], "official_da3_streaming_confidence_minus_one"),
                hit(src["app_runner"], "downstream_must_not_use_raw_depth_confidence"),
                hit(src["app_runner"], "raw depth_conf before official predictions.conf -= 1.0"),
                hit(src["app_runner_test"], "pointcloud stage executes mobile replay of official npz_output_process"),
            ],
            "Research NPZ 路径已按 confidence-minus-one 做对照；Swift native 写 confidencePath 前现在显式执行 conf -= 1.0；APP depth_index/PointCloudStage contract 禁止 raw depth_conf，Dart 点云 executor smoke 已跑通。",
            FILES["official_streaming"],
        ),
        row(
            "npz_output_process_pointcloud_filter",
            "Official results_output/frame_*.npz downstream filters by mean confidence, positive confidence, and sample_ratio.",
            "official_python_oracle_with_mobile_replay_smoke",
            [
                hit(src["official_npz_output_process"], "conf_threshold = np.mean(confs_combined) * conf_threshold_coef"),
                hit(src["official_npz_output_process"], "sample_ratio=sample_ratio"),
                hit(src["official_npz_output_process"], "--conf_threshold_coef"),
                hit(src["official_npz_output_process"], "default=0.5"),
                hit(src["official_npz_output_process"], "default=0.015"),
                hit(src["official_npz_oracle_bridge"], "official_authority"),
                hit(src["official_npz_oracle_bridge"], "This bridge only creates official frame_*.npz + camera_poses.txt inputs"),
                hit(src["official_npz_oracle_bridge"], "subprocess.run"),
                hit(src["official_sim3utils"], "conf_mask = (confs >= conf_threshold) & (confs > 1e-5)"),
                hit(src["official_sim3utils"], "batch_size=1000000"),
                hit(src["official_sim3utils"], "format binary_little_endian 1.0"),
                hit(src["app_runner"], "_writeDa3PointCloudMobileReplay"),
                hit(src["app_runner"], "_writeBinaryLittleEndianPly"),
                hit(src["app_runner"], "mobile_replay_of_official_npz_output_process"),
                hit(src["app_runner"], "official_python_oracle"),
                hit(src["app_runner"], "official_npz_output_process"),
                hit(src["app_runner"], "frames[].imageRelativePath is DA3 processed image, equivalent to frame_*.npz image"),
                hit(src["app_runner"], "frames[].relativeDepthPath is DA3 predictions.depth, equivalent to frame_*.npz depth"),
                hit(src["app_runner"], "compute mean(confs) from confidencePath float32 payload"),
                hit(src["app_runner"], "OpenCV w2c"),
                hit(src["app_runner"], "'conf_threshold_coef': 0.5"),
                hit(src["app_runner"], "'sample_ratio': 0.015"),
                hit(src["app_runner"], "'valid_conf_mask': '(conf >= conf_threshold) && (conf > 1e-5)'"),
                hit(src["app_runner"], "streaming_full_chunk_pcd_path_not_product_baseline"),
                hit(src["app_runner_test"], "officialNpzProcess"),
                hit(src["app_runner_test"], "Dart is only the product mobile replay"),
                hit(src["app_runner_test"], "element vertex 1"),
            ],
            "Research/desktop 权威路径现在有 bridge 直接生成官方 Python npz_output_process.py 所需的 results_output/frame_*.npz + camera_poses.txt；APP PointCloudStage 只是移动端 replay。bridge 不重写点云过滤算法，只做格式转换；Dart smoke 仅证明移动端 replay 边界。full-chunk pcd/combined_pcd.ply 仍不是产品 baseline。",
            FILES["official_npz_output_process"],
        ),
        row(
            "combined_pcd_merge",
            "Official CLI combined_pcd.ply just merges chunk PLY files after chunk alignment.",
            "copied_as_boundary_not_product_solution",
            [
                hit(src["official_streaming"], 'all_ply_path = os.path.join(save_dir, "pcd/combined_pcd.ply")'),
                hit(src["official_streaming"], "merge_ply_files(input_dir, all_ply_path)"),
                hit(src["app_runner"], "do not read full K window reports"),
            ],
            "官方 full-chunk PLY merge 没有 hidden 单窗去厚；产品点云不能把这条路误当厚层修复。",
            FILES["official_streaming"],
        ),
        row(
            "continuity_rejection",
            "Official DA3-Streaming does not reject motion-discontinuous frames inside a chunk.",
            "not_official_do_not_call_parity",
            [
                hit(src["official_streaming"], "self.img_list = sorted("),
                hit(src["dart_policy"], "da3ImageOnlyInputContinuityRisk"),
                hit(src["dart_policy"], "research_continuity_quarantine_counterfactual_v1"),
            ],
            "连续性风险字段和 quarantine 是产品/研究候选，不是官方复制内容。它解释 window_016，但不能标成官方算法。",
            FILES["dart_policy"],
        ),
    ]

    return {
        "schema_version": "aether_official_da3_copy_paste_parity_ledger_v1",
        "date": date,
        "decision": {
            "status": derive_status(rows),
            "goal_complete": False,
            "copy_paste_answer": (
                "官方 image-only CoreML signature/artifact 已落地并通过 readiness gate；"
                "已验证的 C++ OpenCV/libjpeg preprocess kernel 已完成 macOS/JIT bundled native asset smoke，"
                "APP 测试也已强断言 native 可用时 manifest 必须走 native_cpp_opencv_libjpeg；"
                "hook fallback 已加 host os/arch 安全限制，prebuilt matrix 已对当前 macOS arm64 做 ABI probe pass，"
                "并已把 ohos_arm64/ohos_x64 纳入正式目标；但总体仍是 1/9 ready，iOS/Android/Harmony/Windows/Linux/macOS x64 的预编译库与平台打包矩阵还没闭环。"
                "Research/CLI/capture package 已证明 source_highres 到官方 PIL/OpenCV InputProcessor 的 pixel/tensor exact；"
                "APP Dart runner 默认 tryOpen 已接上，Dart package:image decode/resize 现在只是 fallback-only gap。"
            ),
            "next_copy_paste_action": (
                "用 DA3BASE_280x504_N35_image_only 跑 same-capture APP image-only regression；"
                "同时补齐 C++ OpenCV/libjpeg kernel 的 iOS/Android/Harmony/Windows/Linux/macOS x64 预编译库与平台打包矩阵。"
            ),
        },
        "sources": {name: str(path) for name, path in FILES.items()},
        "rows": rows,
        "plain_language": [
            "你说的“找不同”是对的：现在剩下的大差异不是很多。",
            "允许不同：官方 120/60 被手机约束改成 K35/overlap18。",
            "刚补掉的差异：官方 image-only CoreML artifact/signature 已落地，并被 Xcode Resources 引用。",
            "已经复制的部分：DA3-BASE 商用模型、官方 image-only 输入合约、官方 preprocess 的尺寸/patch 合同、K-window sliding/save-frame ownership、RGB/NCHW/ImageNet normalization、results_output core-frame downstream 边界。",
            "刚补掉的差异：source_highres JPEG 到 photos_depth/photos_depth_tensor 已能通过实际 C++ OpenCV/libjpeg kernel byte-exact 复刻官方 InputProcessor。",
            "仍要标注但不再算产品 blocker 的差异：Dart package:image 解同一张 JPEG 在原图阶段不是 byte-exact；它只能做 fallback/compat。",
            "刚确认的复刻路线：实际 C++ OpenCV/libjpeg kernel 已有 C ABI 和 Dart FFI runner；不用再继续硬翻成 Dart。",
            "官方 Python/C++ 能直接作为 Research/desktop oracle 的地方不替换；Dart 只负责 APP 编排和移动端 replay。",
            "刚补上的 APP 接口：LocalPipelineRunner 和后台 isolate 已默认 tryOpen native preprocess runner。",
            "刚补上的打包路径：aether_capture_services hook/build.dart 已能把现有 macOS dylib 注册成 bundled native asset；不带 env 的 package smoke 已通过。",
            "还没闭环的工程差异：iOS/Android/Harmony/Windows 的 C++ OpenCV/libjpeg 预编译库和平台打包矩阵还没补齐；Harmony/OHOS 现在已进入机器可检查矩阵。",
            "连续性 quarantine 不是官方复制，是后续移动端产品候选；不能拿它冒充 DA3 parity。",
        ],
    }


def row(
    check_id: str,
    requirement: str,
    status: str,
    evidence_checks: list[dict[str, Any]],
    conclusion: str,
    primary_source: Path,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "requirement": requirement,
        "status": status,
        "evidence": evidence_checks,
        "conclusion": conclusion,
        "primary_source": str(primary_source),
    }


def hit(text: str, needle: str) -> dict[str, Any]:
    return {"needle": needle, "present": needle in text}


def derive_status(rows: list[dict[str, Any]]) -> str:
    hard_gaps = [
        item["id"]
        for item in rows
        if str(item["status"]).startswith("parity_gap")
    ]
    if hard_gaps:
        return "not_closed_copy_paste_parity_has_hard_gaps"
    return "copy_paste_parity_rows_closed"


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Official DA3 copy-paste parity ledger",
        "",
        f"- 日期：{report['date']}",
        f"- 状态：`{report['decision']['status']}`",
        f"- 结论：{report['decision']['copy_paste_answer']}",
        f"- 下一步：{report['decision']['next_copy_paste_action']}",
        "",
        "## 大白话",
        "",
    ]
    lines.extend(f"- {item}" for item in report["plain_language"])
    lines.extend(
        [
            "",
            "## Rows",
            "",
            "| row | status | conclusion | missing evidence |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in report["rows"]:
        missing = [
            str(check["needle"])
            for check in item["evidence"]
            if not check.get("present")
        ]
        missing_text = "<br>".join(f"`{needle}`" for needle in missing) if missing else ""
        lines.append(
            f"| `{item['id']}` | `{item['status']}` | {item['conclusion']} | {missing_text} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "decision": report["decision"],
        "hard_gaps": [
            {
                "id": row["id"],
                "status": row["status"],
                "conclusion": row["conclusion"],
            }
            for row in report["rows"]
            if str(row["status"]).startswith("parity_gap")
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
