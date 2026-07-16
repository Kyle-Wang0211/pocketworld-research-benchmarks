// Re-sign D against the exact product geometry and 128x72 native JPEG bytes.
//
// This is an experiment harness, not product code.  It deliberately imports
// the current product builders so registered-frame filtering, solved-camera
// Sim(3), source ranking, depth-range quantiles, B ownership, and the
// three-fold reference certificate cannot silently drift from production.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:pocketworld_flutter/capture/bcd_detector_free_job_builder.dart';
import 'package:pocketworld_flutter/capture/bcd_detector_free_scheduler.dart';
import 'package:pocketworld_flutter/capture/bcd_finalize_input_builder.dart';
import 'package:pocketworld_flutter/capture/bcd_finalize_coordinator.dart';
import 'package:pocketworld_flutter/capture/bcd_structural_quality_runner.dart';
import 'package:pocketworld_flutter/capture/sfm_live_recon.dart';
import 'package:pocketworld_flutter/detector_free_depth_ffi.dart';
import 'package:pocketworld_flutter/structural_planesweep_ffi.dart';

Future<void> main(List<String> arguments) async {
  final args = _Args.parse(arguments);
  final started = Stopwatch()..start();
  final rssStart = ProcessInfo.currentRss;
  final ledgerFile = File(args.ledger);
  final sparseFile = File(args.sparsePly);
  final poseMetaFile = File(args.poseMeta);
  final planesFile = File(args.planes);
  final dylibFile = File(Platform.environment['AETHER3D_FFI_DYLIB'] ?? '');
  final fallbackFrameMetaFile = args.fallbackFrameMeta == null
      ? null
      : File(args.fallbackFrameMeta!);
  for (final file in <File>[
    ledgerFile,
    sparseFile,
    poseMetaFile,
    planesFile,
    dylibFile,
    if (fallbackFrameMetaFile != null) fallbackFrameMetaFile,
  ]) {
    if (!file.existsSync()) throw StateError('missing input ${file.path}');
  }

  final ledgerRows = <int, Map<String, Object?>>{};
  for (final line in ledgerFile.readAsLinesSync()) {
    if (line.trim().isEmpty) continue;
    final row = Map<String, Object?>.from(jsonDecode(line) as Map);
    ledgerRows[(row['frameId'] as num).toInt()] = row;
  }
  final poseMeta = Map<String, Object?>.from(
    jsonDecode(poseMetaFile.readAsStringSync()) as Map,
  );
  final poseRows = (poseMeta['poses'] as List)
      .map((item) => Map<String, Object?>.from(item as Map))
      .toList();
  final sparse = _readProductPly(sparseFile);
  final posesPacked = Float64List(poseRows.length * 9);
  for (var index = 0; index < poseRows.length; index++) {
    final row = poseRows[index];
    final q = (row['quat_wxyz'] as List).cast<num>();
    final t = (row['t'] as List).cast<num>();
    final offset = index * 9;
    posesPacked[offset] = (row['frame_id'] as num).toDouble();
    posesPacked[offset + 1] = row['registered'] == true ? 1 : 0;
    for (var axis = 0; axis < 4; axis++) {
      posesPacked[offset + 2 + axis] = q[axis].toDouble();
    }
    for (var axis = 0; axis < 3; axis++) {
      posesPacked[offset + 6 + axis] = t[axis].toDouble();
    }
  }
  final snapshot = SfmLiveSnapshot(
    xyz: sparse.$1,
    rgb: sparse.$2,
    posesPacked: posesPacked,
    summary: Map<String, Object?>.from(
      (poseMeta['summary'] as Map?) ?? const <String, Object?>{},
    ),
    refined: poseMeta['refined'] == true,
    obsOffsets: Int32List(sparse.$1.length ~/ 3 + 1),
    obsFrameIds: Int32List(0),
    obsXY: Float32List(0),
  );

  final dummyGray = File(args.dummyGray);
  final durable = <SfmDurableFedFrameInput>[];
  final registeredIds = <int>{
    for (final row in poseRows)
      if (row['registered'] == true) (row['frame_id'] as num).toInt(),
  };
  final missingJpegs = <int>[];
  final fallbackMetadataFrames = <int>[];
  final inputFiles = <String, String>{};
  final fallbackFrameMeta = fallbackFrameMetaFile == null
      ? null
      : Map<String, Object?>.from(
          jsonDecode(fallbackFrameMetaFile.readAsStringSync()) as Map,
        );
  for (final frameId in registeredIds.toList()..sort()) {
    final legacy = ledgerRows[frameId];
    if (legacy == null) {
      throw StateError('registered frame $frameId is absent from ledger');
    }
    final storedName = File(
      (legacy['jpegPath'] as String),
    ).uri.pathSegments.last;
    final jpeg = File('${args.photos}/$storedName');
    final sidecar = File(
      '${jpeg.path.substring(0, jpeg.path.length - 4)}.json',
    );
    if (!jpeg.existsSync()) missingJpegs.add(frameId);
    final side = sidecar.existsSync()
        ? Map<String, Object?>.from(
            jsonDecode(sidecar.readAsStringSync()) as Map,
          )
        : !jpeg.existsSync() && fallbackFrameMeta != null
        ? Map<String, Object?>.from(fallbackFrameMeta)
        : throw StateError('registered frame $frameId has no AR/JPEG sidecar');
    if (!sidecar.existsSync()) fallbackMetadataFrames.add(frameId);
    final intrinsics = (side['intrinsics_fxfycxcy'] as List).cast<num>();
    final imageW = (side['image_w'] as num).toInt();
    final imageH = (side['image_h'] as num).toInt();
    if (dummyGray.lengthSync() != imageW * imageH) {
      throw StateError(
        'dummy gray length ${dummyGray.lengthSync()} != ${imageW * imageH}',
      );
    }
    final meta = SfmFedFrameMeta(
      jpegPath: jpeg.path,
      imageW: imageW,
      imageH: imageH,
      grayW: imageW,
      grayH: imageH,
      fx: intrinsics[0].toDouble(),
      fy: intrinsics[1].toDouble(),
      cx: intrinsics[2].toDouble(),
      cy: intrinsics[3].toDouble(),
      arkitQuatWxyz: (legacy['arkitCamFromWorldQwxyz'] as List)
          .cast<num>()
          .map((value) => value.toDouble())
          .toList(),
      arkitTransTxyz: (legacy['arkitCamFromWorldTxyz'] as List)
          .cast<num>()
          .map((value) => value.toDouble())
          .toList(),
      arkitCameraCenterWorld: (legacy['arkitCameraCenterWorld'] as List)
          .cast<num>()
          .map((value) => value.toDouble())
          .toList(),
    );
    durable.add(
      SfmDurableFedFrameInput(
        sequence: frameId,
        frameId: frameId,
        grayPath: dummyGray.path,
        meta: meta,
      ),
    );
    if (sidecar.existsSync()) inputFiles[sidecar.path] = _sha256File(sidecar);
    if (jpeg.existsSync()) inputFiles[jpeg.path] = _sha256File(jpeg);
  }

  final buildStarted = Stopwatch()..start();
  final bundle = BcdFinalizeInputBuilder.buildFromDurableFedFrames(
    snapshot: snapshot,
    durableFedFrames: durable,
  );
  var structural = _readStructuralPlanes(planesFile);
  BcdStructuralQualityResult? publicationStructural;
  var structuralExecuteMs = 0.0;
  if (args.publishedPly != null) {
    final missingStructuralAssets = <String>[
      for (final view in bundle.registeredViews)
        if (!File(view.jpegPath).existsSync()) view.jpegPath,
    ];
    if (missingStructuralAssets.isNotEmpty) {
      throw StateError(
        'cannot export an exact B/C/D publication: '
        '${missingStructuralAssets.length} registered JPEG assets are absent',
      );
    }
    final structuralRun = Stopwatch()..start();
    publicationStructural = const BcdStructuralQualityRunner().run(
      sparseXyz: Float32List.fromList(bundle.metricSparseXyz),
      registeredViews: bundle.registeredViews,
    );
    structuralRun.stop();
    structuralExecuteMs = structuralRun.elapsedMicroseconds / 1000.0;
    if (!publicationStructural.qualityPassed ||
        publicationStructural.selectedFloor == null ||
        publicationStructural.certifiedWalls.isEmpty) {
      throw StateError(
        'B/C publication failed closed: '
        '${publicationStructural.rejectedReason}',
      );
    }
    structural = (
      publicationStructural.selectedFloor!,
      publicationStructural.certifiedWalls,
    );
  }
  final nativeReader = _NativeExactAssetReader();
  final buildSet = BcdDetectorFreeJobBuilder.buildAll(
    bundle: bundle,
    assetReader: nativeReader,
    floorValue: structural.$1.planeValue,
    selectedFloor: structural.$1,
    certifiedWalls: structural.$2,
  );
  final captureDigest = _sha256Bytes(
    utf8.encode(
      jsonEncode(<String, Object?>{
        'capture': args.capture,
        'registered': bundle.registeredFrames
            .map((item) => item.frameId)
            .toList(),
        'metric_sparse_sha256': _sha256Float32(bundle.metricSparseXyz),
        'metric_solved_poses_sha256': _sha256Float64(
          bundle.metricSolvedPosesPacked,
        ),
        'native_assets': nativeReader.assets,
      }),
    ),
  );
  final plan = BcdDetectorFreeFullSceneScheduler.buildAll(
    captureDigest: captureDigest,
    backendAbi: _sha256File(dylibFile),
    buildSet: buildSet,
  );
  buildStarted.stop();

  BcdDetectorFreeFullSceneExecution? execution;
  var executeMs = 0.0;
  if (args.execute) {
    final run = Stopwatch()..start();
    execution = BcdDetectorFreeFullSceneScheduler.execute(plan: plan);
    run.stop();
    executeMs = run.elapsedMicroseconds / 1000.0;
  }
  final detailedQuality = args.execute && args.qualityDir != null
      ? _exportDetailedQuality(
          buildSet: buildSet,
          execution: execution!,
          outputDirectory: Directory(args.qualityDir!),
        )
      : null;
  final publication = args.publishedPly == null
      ? null
      : _exportPublishedCloud(
          capture: args.capture,
          outputFile: File(args.publishedPly!),
          originalSparse: sparse,
          bundle: bundle,
          structural: publicationStructural!,
          detectorFree: execution!,
          structuralExecuteMs: structuralExecuteMs,
          detectorFreeExecuteMs: executeMs,
        );
  final detectorFreeBirthExport = args.dBirthsPly == null
      ? null
      : _exportDetectorFreeBirthCloud(
          capture: args.capture,
          outputFile: File(args.dBirthsPly!),
          bundle: bundle,
          detectorFree: execution!,
        );
  started.stop();

  final registeredFrames = <Map<String, Object?>>[
    for (final frame in bundle.registeredFrames)
      <String, Object?>{
        'frame_id': frame.frameId,
        'jpeg': frame.jpegPath,
        'jpeg_exists': File(frame.jpegPath).existsSync(),
        'image': [frame.imageWidth, frame.imageHeight],
        'gray': [frame.grayWidth, frame.grayHeight],
        'gray_k': [frame.grayFx, frame.grayFy, frame.grayCx, frame.grayCy],
        'metric_cam_from_world_q_wxyz': frame.cameraFromWorldQuaternionWxyz,
        'metric_cam_from_world_t_xyz': frame.cameraFromWorldTranslation,
        'native_solve_asset': nativeReader.assets['${frame.frameId}'],
      },
  ];
  final planReferences = <Map<String, Object?>>[
    for (final item in plan.references)
      <String, Object?>{
        'frame_id': item.referenceFrameId,
        'skipped': item.isSkipped,
        'skip_reason': item.skipped?.reason.name,
        'skip_detail': item.skipped?.detail,
        'depth_job_count': item.depthJobCount,
        'depth_job_keys': item.depthJobKeys,
        if (!item.isSkipped)
          'sources': buildSet.plans
              .singleWhere(
                (candidate) =>
                    candidate.referenceFrameId == item.referenceFrameId,
              )
              .sourceFrameIds,
        if (!item.isSkipped)
          'reciprocal_supports': buildSet.plans
              .singleWhere(
                (candidate) =>
                    candidate.referenceFrameId == item.referenceFrameId,
              )
              .reciprocalSupportFrameIds
              .map((key, value) => MapEntry('$key', value)),
        if (!item.isSkipped)
          'descriptors': [
            for (final descriptor
                in buildSet.plans
                    .singleWhere(
                      (candidate) =>
                          candidate.referenceFrameId == item.referenceFrameId,
                    )
                    .depthJobDescriptors)
              <String, Object?>{
                'digest': descriptor.canonicalDigest,
                'reference': descriptor.referenceFrameId,
                'sources': descriptor.sourceFrameIds,
                'gray_plane_digests': descriptor.grayPlaneDigests,
                'inverse_depth_first': descriptor.options.inverseDepthFirst,
                'inverse_depth_step': descriptor.options.inverseDepthStep,
                'depth_count': descriptor.options.depthCount,
                'source_count': descriptor.options.sourceCount,
              },
          ],
      },
  ];
  final executionReferences = execution == null
      ? null
      : <Map<String, Object?>>[
          for (final outcome in execution.outcomes)
            <String, Object?>{
              'frame_id': outcome.referenceFrameId,
              'skipped': outcome.isSkipped,
              'blocked': outcome.isBlocked,
              'certified': outcome.isCertified,
              'pre_certificate_births':
                  outcome.birthResult?.certificate.preCertificateBirthCount ??
                  0,
              'blocked_births':
                  outcome.birthResult?.certificate.blockedBirthCount ?? 0,
              'final_births': outcome.birthCount,
              'failed_fold_mask':
                  outcome.birthResult?.certificate.failedFoldMask ?? 0,
              'floor_owned_candidates': _countMask(
                outcome.birthResult?.ownership.floorOwned,
              ),
              'wall_owned_candidates': _countMask(
                outcome.birthResult?.ownership.wallOwned,
              ),
              'structural_owned_candidates': _countMask(
                outcome.birthResult?.ownership.structuralOwned,
              ),
              'structural_owned_candidates_born_by_d': _maskIntersection(
                outcome.birthResult?.ownership.structuralOwned,
                outcome.birthResult?.certificate.born,
              ),
            },
        ];
  final structuralOwnedTotal = execution == null
      ? 0
      : execution.outcomes.fold<int>(
          0,
          (sum, outcome) =>
              sum + _countMask(outcome.birthResult?.ownership.structuralOwned),
        );
  final structuralConflictBirths = execution == null
      ? 0
      : execution.outcomes.fold<int>(
          0,
          (sum, outcome) =>
              sum +
              _maskIntersection(
                outcome.birthResult?.ownership.structuralOwned,
                outcome.birthResult?.certificate.born,
              ),
        );
  final sim3 = bundle.sim3;
  final result = <String, Object?>{
    'schema': 'pocketworld_d_product_exact_input_certificate_v1',
    'capture': args.capture,
    'executed': args.execute,
    'decision': !args.execute
        ? 'PLANNED_PRODUCT_EXACT_INPUT'
        : args.backendLabel != 'libjpeg_turbo_product'
        ? 'DIAGNOSTIC_ONLY_NONFINAL_JPEG_BACKEND'
        : execution!.blockedReferenceCount == 0
        ? 'PASS_PRODUCT_EXACT_REFERENCE_CERTIFICATE'
        : 'PASS_FAIL_CLOSED_PRODUCT_EXACT_REFERENCE_CERTIFICATE',
    'immutable_inputs': <String, Object?>{
      'ledger': _identity(ledgerFile),
      'sparse_ply': _identity(sparseFile),
      'pose_meta': _identity(poseMetaFile),
      'structural_planes': _identity(planesFile),
      'native_library': _identity(dylibFile),
      'jpeg_backend_label': args.backendLabel,
      'registered_jpeg_and_sidecar_sha256': inputFiles,
      'dummy_gray_note':
          'sparse length-only placeholder; never read because every certified '
          'asset is native-preprocessed directly from its JPEG',
    },
    'product_identity': <String, Object?>{
      'capture_digest': captureDigest,
      'fed_frames': ledgerRows.length,
      'snapshot_pose_rows': poseRows.length,
      'registered_frames': bundle.registeredFrames.length,
      'registered_frame_ids': bundle.registeredFrames
          .map((item) => item.frameId)
          .toList(),
      'missing_registered_jpeg_frame_ids': missingJpegs,
      'registered_frames_using_non_solve_fallback_metadata':
          fallbackMetadataFrames,
      'fallback_metadata_semantics': fallbackFrameMetaFile == null
          ? null
          : <String, Object?>{
              'identity': _identity(fallbackFrameMetaFile),
              'scope': 'registered frames with no JPEG and no sidecar only',
              'solve_effect':
                  'none: asset reader returns null before this K can enter a '
                  'depth job; frame remains available only to solved-pose Sim3',
            },
      'metric_sparse_points': bundle.metricSparseXyz.length ~/ 3,
      'metric_sparse_sha256': _sha256Float32(bundle.metricSparseXyz),
      'metric_solved_poses_sha256': _sha256Float64(
        bundle.metricSolvedPosesPacked,
      ),
      'sim3': <String, Object?>{
        'scale': sim3.scale,
        'rotation_row_major': sim3.rotation,
        'translation': sim3.translation,
        'paired_frame_ids': sim3.pairedFrameIds,
        'residuals': <String, Object?>{
          'pairs': sim3.residuals.pairCount,
          'inliers': sim3.residuals.inlierCount,
          'rmse_m': sim3.residuals.rmse,
          'median_m': sim3.residuals.median,
          'p90_m': sim3.residuals.p90,
          'maximum_m': sim3.residuals.maximum,
          'inlier_threshold_m': sim3.residuals.inlierThreshold,
        },
      },
      'registered_frame_geometry': registeredFrames,
    },
    'certified_policy': <String, Object?>{
      'solve_grid': [128, 72],
      'minimum_sources': 4,
      'maximum_sources': 7,
      'depth_count': 48,
      'depth_quantiles': [0.01, 0.99],
      'depth_padding_fraction': 0.03,
      'patch_n': 5,
      'ncc_min': 0.75,
      'unique_depth_margin': 0.03,
      'minimum_reciprocal_views': 2,
      'minimum_parallax_deg': 8,
      'local_manifold_reference_certificate': true,
    },
    'planning': <String, Object?>{
      'ready_references': plan.readyReferenceCount,
      'skipped_references': plan.skippedReferenceCount,
      'depth_job_uses': plan.depthJobUseCount,
      'unique_depth_jobs': plan.uniqueDepthJobCount,
      'depth_range_evaluations': buildSet.depthRangeEvaluationCount,
      'native_asset_count': nativeReader.assets.length,
      'references': planReferences,
    },
    'execution': execution == null
        ? null
        : <String, Object?>{
            'certified_references': execution.certifiedReferenceCount,
            'blocked_references': execution.blockedReferenceCount,
            'skipped_references': execution.skippedReferenceCount,
            'pre_certificate_births': execution.preCertificateBirthCount,
            'blocked_births': execution.blockedBirthCount,
            'final_births': execution.birthCount,
            'original_sparse_points_removed': 0,
            'b_structural_owned_candidates_not_born_by_d': structuralOwnedTotal,
            'b_structural_conflicts_born_by_d': structuralConflictBirths,
            'cache': <String, Object?>{
              'hits': execution.cacheStats.hits,
              'misses': execution.cacheStats.misses,
              'lru_evictions': execution.cacheStats.lruEvictions,
              'last_use_evictions': execution.cacheStats.lastUseEvictions,
              'peak_bytes': execution.cacheStats.peakBytes,
            },
            'references': executionReferences,
          },
    'detailed_quality_export': detailedQuality,
    'published_cloud': publication,
    'detector_free_birth_cloud': detectorFreeBirthExport,
    'resource': <String, Object?>{
      'build_ms': buildStarted.elapsedMicroseconds / 1000.0,
      'execute_ms': executeMs,
      'total_ms': started.elapsedMicroseconds / 1000.0,
      'rss_start_bytes': rssStart,
      'rss_end_bytes': ProcessInfo.currentRss,
      'rss_delta_bytes': ProcessInfo.currentRss - rssStart,
    },
  };
  final output = File(args.output);
  output.parent.createSync(recursive: true);
  output.writeAsStringSync(
    '${const JsonEncoder.withIndent('  ').convert(result)}\n',
  );
  stdout.writeln(
    jsonEncode(<String, Object?>{
      'capture': args.capture,
      'output': output.path,
      'ready': plan.readyReferenceCount,
      'skipped': plan.skippedReferenceCount,
      'births': execution?.birthCount,
      'blocked': execution?.blockedReferenceCount,
      'elapsed_ms': started.elapsedMicroseconds / 1000.0,
    }),
  );
}

Map<String, Object?> _exportDetectorFreeBirthCloud({
  required String capture,
  required File outputFile,
  required BcdFinalizeInputBundle bundle,
  required BcdDetectorFreeFullSceneExecution detectorFree,
}) {
  final cloud = bundle.metricBirthToSnapshot(
    detectorFree.mergedMetricBirthCloud,
  );
  if (cloud.pointCount != detectorFree.birthCount ||
      cloud.xyz.length != cloud.rgb.length ||
      cloud.xyz.any((value) => !value.isFinite)) {
    throw StateError('D birth cloud does not match certified execution');
  }
  _writeProductPly(outputFile, cloud.xyz, cloud.rgb);
  final reread = _readProductPly(outputFile);
  final xyzBytes = cloud.xyz.buffer.asUint8List(
    cloud.xyz.offsetInBytes,
    cloud.xyz.lengthInBytes,
  );
  if (!_bytesEqual(
        reread.$1.buffer.asUint8List(
          reread.$1.offsetInBytes,
          reread.$1.lengthInBytes,
        ),
        xyzBytes,
      ) ||
      !_bytesEqual(reread.$2, cloud.rgb)) {
    throw StateError('D true-color PLY serialization failed byte round-trip');
  }
  var nonzeroRgbPoints = 0;
  for (var index = 0; index < cloud.pointCount; index++) {
    if (cloud.rgb[index * 3] != 0 ||
        cloud.rgb[index * 3 + 1] != 0 ||
        cloud.rgb[index * 3 + 2] != 0) {
      nonzeroRgbPoints++;
    }
  }
  final manifest = <String, Object?>{
    'schema': 'pocketworld_exact_d_true_color_birth_cloud_v1',
    'capture': capture,
    'decision': 'PASS_EXACT_D_TRUE_COLOR_BIRTH_EXPORT',
    'coordinate_gauge': 'original_sparse_snapshot_via_inverse_product_sim3',
    'point_order': 'scheduler_reference_then_row_major_certified_births',
    'points': cloud.pointCount,
    'rgb_nonzero_points': nonzeroRgbPoints,
    'rgb_nonzero_rate': cloud.pointCount == 0
        ? 0.0
        : nonzeroRgbPoints / cloud.pointCount,
    'ply': _identity(outputFile),
  };
  final manifestFile = File('${outputFile.path}.manifest.json');
  manifestFile.writeAsStringSync(
    '${const JsonEncoder.withIndent('  ').convert(manifest)}\n',
  );
  return <String, Object?>{...manifest, 'manifest': _identity(manifestFile)};
}

Map<String, Object?> _exportPublishedCloud({
  required String capture,
  required File outputFile,
  required (Float32List, Uint8List) originalSparse,
  required BcdFinalizeInputBundle bundle,
  required BcdStructuralQualityResult structural,
  required BcdDetectorFreeFullSceneExecution detectorFree,
  required double structuralExecuteMs,
  required double detectorFreeExecuteMs,
}) {
  final structuralClouds = <BcdPointCloud>[
    for (final birth in structural.structuralBirths)
      bundle.metricBirthToSnapshot(birth.cloud),
  ];
  final detectorFreeCloud = bundle.metricBirthToSnapshot(
    detectorFree.mergedMetricBirthCloud,
  );
  final originalPoints = originalSparse.$1.length ~/ 3;
  final structuralPoints = structuralClouds.fold<int>(
    0,
    (sum, cloud) => sum + cloud.pointCount,
  );
  final totalPoints =
      originalPoints + structuralPoints + detectorFreeCloud.pointCount;
  final xyz = Float32List(totalPoints * 3);
  final rgb = Uint8List(totalPoints * 3);
  var offset = 0;
  void append(BcdPointCloud cloud) {
    xyz.setAll(offset, cloud.xyz);
    rgb.setAll(offset, cloud.rgb);
    offset += cloud.xyz.length;
  }

  append(BcdPointCloud(xyz: originalSparse.$1, rgb: originalSparse.$2));
  for (final cloud in structuralClouds) {
    append(cloud);
  }
  append(detectorFreeCloud);
  final originalXyzBytes = originalSparse.$1.buffer.asUint8List(
    originalSparse.$1.offsetInBytes,
    originalSparse.$1.lengthInBytes,
  );
  final originalRgbBytes = originalSparse.$2.buffer.asUint8List(
    originalSparse.$2.offsetInBytes,
    originalSparse.$2.lengthInBytes,
  );
  final xyzBytes = xyz.buffer.asUint8List(xyz.offsetInBytes, xyz.lengthInBytes);
  final rgbBytes = rgb.buffer.asUint8List(rgb.offsetInBytes, rgb.lengthInBytes);
  if (!_bytesPrefixEqual(xyzBytes, originalXyzBytes) ||
      !_bytesPrefixEqual(rgbBytes, originalRgbBytes)) {
    throw StateError('published cloud changed original sparse prefix bytes');
  }
  _writeProductPly(outputFile, xyz, rgb);
  final reread = _readProductPly(outputFile);
  if (!_bytesEqual(
        reread.$1.buffer.asUint8List(
          reread.$1.offsetInBytes,
          reread.$1.lengthInBytes,
        ),
        xyzBytes,
      ) ||
      !_bytesEqual(reread.$2, rgbBytes)) {
    throw StateError('published PLY serialization failed byte round-trip');
  }
  var nonzeroRgbPoints = 0;
  for (var index = 0; index < totalPoints; index++) {
    if (rgb[index * 3] != 0 ||
        rgb[index * 3 + 1] != 0 ||
        rgb[index * 3 + 2] != 0) {
      nonzeroRgbPoints++;
    }
  }
  final manifest = <String, Object?>{
    'schema': 'pocketworld_full_true_color_publication_v1',
    'capture': capture,
    'decision': 'PASS_EXACT_FULL_TRUE_COLOR_PUBLICATION',
    'order': ['original_sparse', 'b_structural_births', 'd_births'],
    'original_sparse_points': originalPoints,
    'b_structural_births': structuralPoints,
    'd_births': detectorFreeCloud.pointCount,
    'total_points': totalPoints,
    'original_sparse_prefix_xyz_exact': true,
    'original_sparse_prefix_rgb_exact': true,
    'rgb_nonzero_points': nonzeroRgbPoints,
    'rgb_nonzero_rate': totalPoints == 0 ? 0.0 : nonzeroRgbPoints / totalPoints,
    'timing_ms': <String, Object?>{
      'b_structural': structuralExecuteMs,
      'd_detector_free': detectorFreeExecuteMs,
    },
    'ply': _identity(outputFile),
  };
  final manifestFile = File('${outputFile.path}.manifest.json');
  manifestFile.writeAsStringSync(
    '${const JsonEncoder.withIndent('  ').convert(manifest)}\n',
  );
  return <String, Object?>{...manifest, 'manifest': _identity(manifestFile)};
}

void _writeProductPly(File file, Float32List xyz, Uint8List rgb) {
  if (xyz.length != rgb.length || xyz.length % 3 != 0) {
    throw ArgumentError('malformed publication cloud');
  }
  final count = xyz.length ~/ 3;
  final header = ascii.encode(
    'ply\n'
    'format binary_little_endian 1.0\n'
    'comment PocketWorld append-only B/C/D publication\n'
    'element vertex $count\n'
    'property float x\n'
    'property float y\n'
    'property float z\n'
    'property uchar red\n'
    'property uchar green\n'
    'property uchar blue\n'
    'end_header\n',
  );
  final body = Uint8List(count * 15);
  final data = ByteData.sublistView(body);
  for (var index = 0; index < count; index++) {
    final source = index * 3;
    final target = index * 15;
    data.setFloat32(target, xyz[source], Endian.little);
    data.setFloat32(target + 4, xyz[source + 1], Endian.little);
    data.setFloat32(target + 8, xyz[source + 2], Endian.little);
    body[target + 12] = rgb[source];
    body[target + 13] = rgb[source + 1];
    body[target + 14] = rgb[source + 2];
  }
  file.parent.createSync(recursive: true);
  file.writeAsBytesSync(<int>[...header, ...body], flush: true);
}

bool _bytesPrefixEqual(Uint8List bytes, Uint8List prefix) {
  if (bytes.length < prefix.length) return false;
  for (var index = 0; index < prefix.length; index++) {
    if (bytes[index] != prefix[index]) return false;
  }
  return true;
}

bool _bytesEqual(Uint8List left, Uint8List right) =>
    left.length == right.length && _bytesPrefixEqual(left, right);

Map<String, Object?> _exportDetailedQuality({
  required BcdDetectorFreeJobBuildSet buildSet,
  required BcdDetectorFreeFullSceneExecution execution,
  required Directory outputDirectory,
}) {
  outputDirectory.createSync(recursive: true);
  final sparse = buildSet.plans.first.metadata.metricSparseXyz;
  final sparseFile = File('${outputDirectory.path}/metric_sparse_f32le.bin');
  sparseFile.writeAsBytesSync(
    sparse.buffer.asUint8List(sparse.offsetInBytes, sparse.lengthInBytes),
  );
  final runner = const BcdFfiDetectorFreeDepthRunner();
  final references = <Map<String, Object?>>[];
  var totalProductMaskMismatches = 0;
  var totalFloorMaskMismatches = 0;
  var totalWallMaskMismatches = 0;
  var totalStructuralMaskMismatches = 0;
  for (final plan in buildSet.plans) {
    final metadata = plan.metadata;
    final primaryJob = plan.materializePrimaryDepthJob();
    final primary = runner.runDepth(primaryJob);
    final width = primaryJob.options.imageWidth;
    final height = primaryJob.options.imageHeight;
    final pixels = width * height;
    final reciprocalDepths = Float32List(plan.reciprocalCount * pixels);
    final reciprocalAccepted = Uint8List(plan.reciprocalCount * pixels);
    final reciprocalIdentityDepths = Float32List(plan.reciprocalCount * pixels);
    final reciprocalIdentityAccepted = Uint8List(plan.reciprocalCount * pixels);
    for (var index = 0; index < plan.reciprocalCount; index++) {
      final depth = runner.runDepth(plan.materializeReciprocalDepthJob(index));
      reciprocalDepths.setRange(
        index * pixels,
        (index + 1) * pixels,
        depth.depthM,
      );
      reciprocalAccepted.setRange(
        index * pixels,
        (index + 1) * pixels,
        depth.accepted,
      );
      reciprocalIdentityDepths.setRange(
        index * pixels,
        (index + 1) * pixels,
        depth.identityDepthM,
      );
      reciprocalIdentityAccepted.setRange(
        index * pixels,
        (index + 1) * pixels,
        depth.identityAccepted,
      );
    }
    final reciprocalIdentity = runner.filterReciprocal(
      BcdDetectorFreeReciprocalInput(
        imageWidth: width,
        imageHeight: height,
        referenceInverseK: Float32List.fromList(
          primaryJob.options.referenceInverseK,
        ),
        referenceDepthM: primary.identityDepthM,
        referenceAccepted: primary.identityAccepted,
        reciprocalDepthsM: reciprocalIdentityDepths,
        reciprocalAccepted: reciprocalIdentityAccepted,
        referenceToReciprocalProjections:
            metadata.referenceToReciprocalProjections,
        reciprocalCameraCentersInReference:
            metadata.reciprocalCameraCentersInReference,
        options: metadata.reciprocalOptions,
      ),
    );
    final reciprocalMetric = runner.filterReciprocal(
      BcdDetectorFreeReciprocalInput(
        imageWidth: width,
        imageHeight: height,
        referenceInverseK: Float32List.fromList(
          primaryJob.options.referenceInverseK,
        ),
        referenceDepthM: primary.depthM,
        referenceAccepted: primary.accepted,
        reciprocalDepthsM: reciprocalDepths,
        reciprocalAccepted: reciprocalAccepted,
        referenceToReciprocalProjections:
            metadata.referenceToReciprocalProjections,
        reciprocalCameraCentersInReference:
            metadata.reciprocalCameraCentersInReference,
        options: metadata.reciprocalOptions,
      ),
    );
    final publicationDepth = Float32List.fromList(primary.identityDepthM);
    for (var index = 0; index < pixels; index++) {
      if (reciprocalIdentity.born[index] != 0 &&
          reciprocalMetric.born[index] != 0) {
        publicationDepth[index] = primary.depthM[index];
      }
    }
    final candidateXyz = _unprojectCandidates(
      width: width,
      height: height,
      inverseK: primaryJob.options.referenceInverseK,
      worldToReferenceProjection3x4: metadata.worldToReferenceProjection3x4,
      depthM: publicationDepth,
      eligible: reciprocalIdentity.born,
    );
    final gated = BcdFinalizeCoordinator.gateDetectorFreeCandidates(
      sparseXyz: metadata.metricSparseXyz,
      candidateXyz: candidateXyz,
      candidateRgb: metadata.referenceRgb,
      reciprocalBorn: reciprocalIdentity.born,
      floorValue: metadata.floorValue,
      selectedFloor: metadata.selectedFloor,
      certifiedWalls: metadata.certifiedWalls,
      options: metadata.localManifoldOptions,
    );
    final scheduled = execution.outcomes.singleWhere(
      (outcome) => outcome.referenceFrameId == plan.referenceFrameId,
    );
    final scheduledBirth = scheduled.birthResult!;
    final floorMismatches = _maskMismatches(
      gated.ownership.floorOwned,
      scheduledBirth.ownership.floorOwned,
    );
    final wallMismatches = _maskMismatches(
      gated.ownership.wallOwned,
      scheduledBirth.ownership.wallOwned,
    );
    final structuralMismatches = _maskMismatches(
      gated.ownership.structuralOwned,
      scheduledBirth.ownership.structuralOwned,
    );
    final productMismatches = _maskMismatches(
      gated.ownership.certificate.born,
      scheduledBirth.ownership.certificate.born,
    );
    totalFloorMaskMismatches += floorMismatches;
    totalWallMaskMismatches += wallMismatches;
    totalStructuralMaskMismatches += structuralMismatches;
    totalProductMaskMismatches += productMismatches;

    // Fixed 17-byte row: XYZ float32 little-endian followed by
    // reciprocal-eligible, floor-owned, wall-owned, structural-owned, and
    // post-certificate product-born uint8 masks. All pixels are retained so
    // the independent evaluator can prove bit-exact ownership, including the
    // ineligible zero-XYZ rows used by the ABI.
    const stride = 17;
    final rows = Uint8List(pixels * stride);
    final bytes = ByteData.sublistView(rows);
    for (var index = 0; index < pixels; index++) {
      final offset = index * stride;
      bytes.setFloat32(offset, candidateXyz[index * 3], Endian.little);
      bytes.setFloat32(offset + 4, candidateXyz[index * 3 + 1], Endian.little);
      bytes.setFloat32(offset + 8, candidateXyz[index * 3 + 2], Endian.little);
      rows[offset + 12] = reciprocalIdentity.born[index];
      rows[offset + 13] = gated.ownership.floorOwned[index];
      rows[offset + 14] = gated.ownership.wallOwned[index];
      rows[offset + 15] = gated.ownership.structuralOwned[index];
      rows[offset + 16] = gated.ownership.certificate.born[index];
    }
    final candidateFile = File(
      '${outputDirectory.path}/reference_${plan.referenceFrameId}.rows17.bin',
    );
    candidateFile.writeAsBytesSync(rows);
    references.add(<String, Object?>{
      'reference_frame_id': plan.referenceFrameId,
      'source_frame_ids': plan.sourceFrameIds,
      'width': width,
      'height': height,
      'row_stride_bytes': stride,
      'candidate_file': _identity(candidateFile),
      'reciprocal_eligible': _countMask(reciprocalIdentity.born),
      'floor_owned': _countMask(gated.ownership.floorOwned),
      'wall_owned': _countMask(gated.ownership.wallOwned),
      'structural_owned': _countMask(gated.ownership.structuralOwned),
      'pre_certificate_births':
          gated.ownership.certificate.preCertificateBirthCount,
      'blocked_births': gated.ownership.certificate.blockedBirthCount,
      'product_births': _countMask(gated.ownership.certificate.born),
      'failed_fold_mask': gated.ownership.certificate.failedFoldMask,
      'scheduler_parity': <String, Object?>{
        'floor_mask_mismatches': floorMismatches,
        'wall_mask_mismatches': wallMismatches,
        'structural_mask_mismatches': structuralMismatches,
        'product_birth_mask_mismatches': productMismatches,
      },
    });
  }
  final manifest = <String, Object?>{
    'schema': 'pocketworld_product_exact_d_quality_rows_v1',
    'metric_sparse': <String, Object?>{
      ..._identity(sparseFile),
      'points': sparse.length ~/ 3,
      'storage': 'float32_little_endian_xyz',
    },
    'candidate_row_schema': <String>[
      'x_f32le',
      'y_f32le',
      'z_f32le',
      'reciprocal_eligible_u8',
      'floor_owned_u8',
      'wall_owned_u8',
      'structural_owned_u8',
      'post_certificate_product_born_u8',
    ],
    'scheduler_parity': <String, Object?>{
      'floor_mask_mismatches': totalFloorMaskMismatches,
      'wall_mask_mismatches': totalWallMaskMismatches,
      'structural_mask_mismatches': totalStructuralMaskMismatches,
      'product_birth_mask_mismatches': totalProductMaskMismatches,
      'exact':
          totalFloorMaskMismatches == 0 &&
          totalWallMaskMismatches == 0 &&
          totalStructuralMaskMismatches == 0 &&
          totalProductMaskMismatches == 0,
    },
    'references': references,
  };
  final manifestFile = File('${outputDirectory.path}/manifest.json');
  manifestFile.writeAsStringSync(
    '${const JsonEncoder.withIndent('  ').convert(manifest)}\n',
  );
  return <String, Object?>{
    'manifest': _identity(manifestFile),
    'scheduler_parity': manifest['scheduler_parity'],
  };
}

int _maskMismatches(Uint8List left, Uint8List right) {
  if (left.length != right.length) return -1;
  var mismatches = 0;
  for (var index = 0; index < left.length; index++) {
    if (left[index] != right[index]) mismatches++;
  }
  return mismatches;
}

Float32List _unprojectCandidates({
  required int width,
  required int height,
  required List<double> inverseK,
  required Float32List worldToReferenceProjection3x4,
  required Float32List depthM,
  required Uint8List eligible,
}) {
  final e = List<double>.filled(12, 0);
  for (var row = 0; row < 3; row++) {
    for (var column = 0; column < 4; column++) {
      e[row * 4 + column] =
          inverseK[row * 3] * worldToReferenceProjection3x4[column] +
          inverseK[row * 3 + 1] * worldToReferenceProjection3x4[4 + column] +
          inverseK[row * 3 + 2] * worldToReferenceProjection3x4[8 + column];
    }
  }
  final xyz = Float32List(width * height * 3);
  for (var y = 0; y < height; y++) {
    for (var x = 0; x < width; x++) {
      final index = y * width + x;
      if (eligible[index] == 0) continue;
      final depth = depthM[index];
      final cameraX = (inverseK[0] * x + inverseK[1] * y + inverseK[2]) * depth;
      final cameraY = (inverseK[3] * x + inverseK[4] * y + inverseK[5]) * depth;
      final cameraZ = (inverseK[6] * x + inverseK[7] * y + inverseK[8]) * depth;
      final centeredX = cameraX - e[3];
      final centeredY = cameraY - e[7];
      final centeredZ = cameraZ - e[11];
      xyz[index * 3] = e[0] * centeredX + e[4] * centeredY + e[8] * centeredZ;
      xyz[index * 3 + 1] =
          e[1] * centeredX + e[5] * centeredY + e[9] * centeredZ;
      xyz[index * 3 + 2] =
          e[2] * centeredX + e[6] * centeredY + e[10] * centeredZ;
    }
  }
  return xyz;
}

final class _NativeExactAssetReader implements BcdDetectorFreeAssetReader {
  final Map<String, Object?> assets = <String, Object?>{};

  @override
  BcdDetectorFreeSolveAsset? readSolveAsset(
    BcdFinalizeRegisteredFrameInput input, {
    required int width,
    required int height,
  }) {
    final frame = input.cameraFrame;
    if (!File(frame.jpegPath).existsSync()) return null;
    final preprocessed = DetectorFreeImagePreprocessor.fromJpegPath(
      jpegPath: frame.jpegPath,
      sourceK: <double>[
        frame.grayFx,
        0,
        frame.grayCx,
        0,
        frame.grayFy,
        frame.grayCy,
        0,
        0,
        1,
      ],
    );
    if (preprocessed.width != width || preprocessed.height != height) {
      throw StateError('native solve grid changed');
    }
    final grayDigest = _sha256Bytes(preprocessed.grayU8);
    final rgbDigest = _sha256Bytes(preprocessed.rgbU8);
    assets['${frame.frameId}'] = <String, Object?>{
      'source': 'aether_detector_free_preprocess_jpeg_path',
      'jpeg_sha256': _sha256File(File(frame.jpegPath)),
      'source_size': [preprocessed.sourceWidth, preprocessed.sourceHeight],
      'solve_size': [preprocessed.width, preprocessed.height],
      'scale': [preprocessed.scaleX, preprocessed.scaleY],
      'scaled_k_float32': preprocessed.scaledK.toList(),
      'rgb_u8_sha256': rgbDigest,
      'gray_u8_sha256': grayDigest,
    };
    return BcdDetectorFreeSolveAsset(
      frameId: frame.frameId,
      width: width,
      height: height,
      gray: preprocessed.grayU8,
      rgb: preprocessed.rgbU8,
      grayDigest: grayDigest,
      rgbDigest: rgbDigest,
      provenance: BcdDetectorFreePhotometricProvenance.jpegRgbArea,
    );
  }
}

(StructuralFloorDomain, List<StructuralWall>) _readStructuralPlanes(File file) {
  final json = Map<String, Object?>.from(
    jsonDecode(file.readAsStringSync()) as Map,
  );
  final floorJson = Map<String, Object?>.from(json['floor'] as Map);
  final floor = StructuralFloorDomain(
    certified: true,
    normal: _doubles(floorJson['normal']),
    basisU: _doubles(floorJson['basis_u']),
    basisV: _doubles(floorJson['basis_v']),
    planeValue: (floorJson['plane_value_n_dot_x'] as num).toDouble(),
    boundsU: _doubles(floorJson['bounds_u_m']),
    boundsV: _doubles(floorJson['bounds_v_m']),
  );
  final selected = (json['selected_surface_ids'] as List)
      .cast<String>()
      .toSet();
  final walls = <StructuralWall>[];
  for (final raw in (json['surfaces'] as List).cast<Map>()) {
    final wall = Map<String, Object?>.from(raw);
    if (!selected.contains(wall['surface_id']) ||
        wall['certified_for_generation'] != true ||
        wall['kind'] != 'wall') {
      continue;
    }
    walls.add(
      StructuralWall(
        index: walls.length,
        thetaDeg: ((wall['theta_deg_in_horizontal_basis'] as num?) ?? 0)
            .round(),
        certified: true,
        supportPoints35mm: (wall['support_points_35mm'] as num?)?.toInt() ?? 0,
        coverageCells10cm: (wall['coverage_cells_10cm'] as num?)?.toInt() ?? 0,
        domainPoints: (wall['domain_points'] as num?)?.toInt() ?? 0,
        supportPoints20mm: _ints(
          wall['support_points_20mm_offsets_minus10_to_plus10cm'],
          5,
        ),
        supportCells10cm: _ints(
          wall['support_cells_10cm_offsets_minus10_to_plus10cm'],
          5,
        ),
        normal: _doubles(wall['normal']),
        basisU: _doubles(wall['basis_u']),
        basisV: _doubles(wall['basis_v']),
        planeValue: (wall['plane_value_n_dot_x'] as num).toDouble(),
        boundsU: _doubles(wall['bounds_u_m']),
        boundsHeight: _doubles(wall['bounds_height_m']),
        score: (wall['score'] as num?)?.toDouble() ?? 0,
        supportProminenceVs5cm:
            (wall['support_prominence_vs_5cm'] as num?)?.toDouble() ?? 0,
        coverageProminenceVs5cm:
            (wall['coverage_prominence_vs_5cm'] as num?)?.toDouble() ?? 0,
      ),
    );
  }
  return (floor, List<StructuralWall>.unmodifiable(walls));
}

List<double> _doubles(Object? value) => (value as List)
    .cast<num>()
    .map((item) => item.toDouble())
    .toList(growable: false);

List<int> _ints(Object? value, int length) {
  if (value is! List) return List<int>.filled(length, 0);
  final result = value.cast<num>().map((item) => item.toInt()).toList();
  return result.length == length ? result : List<int>.filled(length, 0);
}

(Float32List, Uint8List) _readProductPly(File file) {
  final bytes = file.readAsBytesSync();
  const marker = 'end_header\n';
  final markerBytes = ascii.encode(marker);
  var headerEnd = -1;
  for (var offset = 0; offset <= bytes.length - markerBytes.length; offset++) {
    var match = true;
    for (var index = 0; index < markerBytes.length; index++) {
      if (bytes[offset + index] != markerBytes[index]) {
        match = false;
        break;
      }
    }
    if (match) {
      headerEnd = offset + markerBytes.length;
      break;
    }
  }
  if (headerEnd < 0) throw StateError('PLY has no end_header');
  final header = ascii.decode(bytes.sublist(0, headerEnd));
  final match = RegExp(r'element vertex (\d+)').firstMatch(header);
  if (!header.contains('format binary_little_endian 1.0') || match == null) {
    throw StateError('unsupported PLY format');
  }
  final count = int.parse(match.group(1)!);
  const stride = 15;
  if (bytes.length != headerEnd + count * stride) {
    throw StateError('PLY byte count does not match 15-byte vertex stride');
  }
  final data = ByteData.sublistView(bytes);
  final xyz = Float32List(count * 3);
  final rgb = Uint8List(count * 3);
  for (var index = 0; index < count; index++) {
    final source = headerEnd + index * stride;
    final target = index * 3;
    xyz[target] = data.getFloat32(source, Endian.little);
    xyz[target + 1] = data.getFloat32(source + 4, Endian.little);
    xyz[target + 2] = data.getFloat32(source + 8, Endian.little);
    rgb[target] = bytes[source + 12];
    rgb[target + 1] = bytes[source + 13];
    rgb[target + 2] = bytes[source + 14];
  }
  return (xyz, rgb);
}

Map<String, Object?> _identity(File file) => <String, Object?>{
  'path': file.absolute.path,
  'bytes': file.lengthSync(),
  'sha256': _sha256File(file),
};

String _sha256File(File file) =>
    sha256.convert(file.readAsBytesSync()).toString();
String _sha256Bytes(List<int> bytes) => sha256.convert(bytes).toString();
String _sha256Float32(Float32List values) => _sha256Bytes(
  values.buffer.asUint8List(values.offsetInBytes, values.lengthInBytes),
);
String _sha256Float64(Float64List values) => _sha256Bytes(
  values.buffer.asUint8List(values.offsetInBytes, values.lengthInBytes),
);

int _countMask(Uint8List? mask) =>
    mask?.fold<int>(0, (sum, value) => sum + (value == 0 ? 0 : 1)) ?? 0;

int _maskIntersection(Uint8List? left, Uint8List? right) {
  if (left == null || right == null) return 0;
  if (left.length != right.length) throw StateError('mask length mismatch');
  var count = 0;
  for (var index = 0; index < left.length; index++) {
    if (left[index] != 0 && right[index] != 0) count++;
  }
  return count;
}

final class _Args {
  const _Args({
    required this.capture,
    required this.ledger,
    required this.photos,
    required this.sparsePly,
    required this.poseMeta,
    required this.planes,
    required this.dummyGray,
    required this.output,
    required this.execute,
    required this.backendLabel,
    required this.qualityDir,
    required this.fallbackFrameMeta,
    required this.publishedPly,
    required this.dBirthsPly,
  });

  final String capture;
  final String ledger;
  final String photos;
  final String sparsePly;
  final String poseMeta;
  final String planes;
  final String dummyGray;
  final String output;
  final bool execute;
  final String backendLabel;
  final String? qualityDir;
  final String? fallbackFrameMeta;
  final String? publishedPly;
  final String? dBirthsPly;

  static _Args parse(List<String> values) {
    final map = <String, String>{};
    var execute = false;
    for (var index = 0; index < values.length; index++) {
      if (values[index] == '--execute') {
        execute = true;
        continue;
      }
      if (!values[index].startsWith('--') || index + 1 >= values.length) {
        throw ArgumentError('invalid argument ${values[index]}');
      }
      map[values[index].substring(2)] = values[++index];
    }
    String need(String key) =>
        map[key] ?? (throw ArgumentError('missing --$key'));
    return _Args(
      capture: need('capture'),
      ledger: need('ledger'),
      photos: need('photos'),
      sparsePly: need('sparse-ply'),
      poseMeta: need('pose-meta'),
      planes: need('planes'),
      dummyGray: need('dummy-gray'),
      output: need('output'),
      execute: execute,
      backendLabel: map['backend-label'] ?? 'unspecified_diagnostic',
      qualityDir: map['quality-dir'],
      fallbackFrameMeta: map['fallback-frame-meta'],
      publishedPly: map['published-ply'],
      dBirthsPly: map['d-births-ply'],
    );
  }
}
