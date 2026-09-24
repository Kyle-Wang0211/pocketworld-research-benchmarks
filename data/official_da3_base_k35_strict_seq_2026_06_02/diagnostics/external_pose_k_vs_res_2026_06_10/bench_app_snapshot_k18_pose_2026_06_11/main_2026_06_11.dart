// DA3-BASE pose-conditioned K=18 @ 504x896 3-window iPhone CoreML spike
//
// Auto-fires on launch: 3 sliding windows (frames 0-17 / 9-26 / 17-34, 50%
// overlap) of the strict K35 capture through DA3BASE_504x896_N18_pose
// (image + raw ARKit w2c extrinsics + processed-scale intrinsics).
// 41,490 tokens — highest phone-legal K18 rung (predict limit 43,260).
// Goal: RSS peak + per-window latency + cross-window overlap consistency
// + Mac parity.
//
// Inputs are PRE-COMPUTED fp32 CHW tensors from the official InputProcessor
// (upper_bound_resize + ImageNet normalization) plus pose_frames.json carrying
// cameraExtrinsicOpenCvW2c4x4 / cameraIntrinsic3x3 per frame — bit-identical
// to the Mac PyTorch ladder_k18_res896 reference.
//
// NOT production — sibling spike app to keep pocketworld_flutter clean.

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

void main() => runApp(const Da3BenchApp());

class Da3BenchApp extends StatelessWidget {
  const Da3BenchApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'DA3 K90 414f Bench',
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
      home: const BenchPage(),
    );
  }
}

class BenchPage extends StatefulWidget {
  const BenchPage({super.key});
  @override
  State<BenchPage> createState() => _BenchPageState();
}

class _BenchPageState extends State<BenchPage> {
  // Use pocketworld_flutter's proven Da3DepthPlugin (channel + method),
  // copied verbatim into this bench app.
  static const _channel = MethodChannel('pocketworld/da3_depth');
  static const _memChannel = MethodChannel('da3_bench/mem');
  // Pose-conditioned spike: K=18 @ 504x896 = 18*2305+... = 41,490 tokens,
  // the highest phone-legal K18 rung (predict limit pinned at 43,260~44,460).
  // 504x896 is also inside DA3's trained resolution list (896x504) and won
  // the Mac quality ladder (conf med 10.10, residual med 0.25%).
  static const _modelName = 'DA3BASE_504x896_N18_pose';
  static const _windowSize = 18;
  static const _overlap = 9;
  static const _stride = _windowSize - _overlap;
  static const _totalFrames = 35;
  static const _inputHeight = 504;
  static const _inputWidth = 896;
  static const _assetDir = 'assets/test_tensors_504x896_n18';
  static const _perFrameBytes = 3 * 504 * 896 * 4; // 5,419,008
  static const _autoFire = bool.fromEnvironment(
    'POCKETWORLD_AUTO_BENCH',
    defaultValue: true,
  );
  // Cap windows for quick metric probes (0 = run all). 3 windows gives
  // overlap pairs 0-1 and 1-2 — enough for cross-resolution comparison
  // at ~10% of a full run's wall time.
  static const _maxWindows = int.fromEnvironment(
    'POCKETWORLD_BENCH_MAX_WINDOWS',
    defaultValue: 0,
  );

  final _logs = <String>[];
  final _scroll = ScrollController();
  bool _running = false;
  Directory? _tensorDir;
  Directory? _runRoot;

  @override
  void initState() {
    super.initState();
    if (_autoFire) {
      WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_runBench()));
    }
  }

  void _log(String s) {
    if (!mounted) return;
    final ts = DateTime.now().toIso8601String().substring(11, 19);
    setState(() => _logs.add('$ts $s'));
    debugPrint('[da3_bench] $s');
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });
  }

  Future<Map<String, dynamic>> _mem() async {
    try {
      final r = await _memChannel.invokeMapMethod<String, dynamic>('snapshot');
      return r ?? const {};
    } catch (_) {
      return const {};
    }
  }

  Future<void> _runBench() async {
    if (_running) return;
    setState(() => _running = true);
    final stopwatch = Stopwatch()..start();
    try {
      _log('=== DA3 K90 image-only 414f bench start ===');
      _log('model=$_modelName, K=$_windowSize, overlap=$_overlap, total=$_totalFrames');

      await _prepareTestTensors();

      _log('memBefore=${await _mem()}');

      var numChunks =
          ((_totalFrames - _overlap + _stride - 1) ~/ _stride);
      if (_maxWindows > 0 && _maxWindows < numChunks) {
        numChunks = _maxWindows;
        _log('numChunks capped to $_maxWindows (quick metric probe)');
      } else {
        _log('numChunks=$numChunks (official DA3-Streaming formula)');
      }

      final docs = await getApplicationDocumentsDirectory();
      _runRoot = Directory(
        '${docs.path}/da3_bench_run_${DateTime.now().microsecondsSinceEpoch}',
      );
      await _runRoot!.create(recursive: true);
      _log('runRoot=${_runRoot!.path}');

      final summaries = <Map<String, dynamic>>[];
      for (var pass = 0; pass < numChunks; pass += 1) {
        var start = pass * _stride;
        if (start + _windowSize > _totalFrames) {
          start = _totalFrames - _windowSize;
        }
        final passLabel = pass.toString().padLeft(3, '0');
        final outDir = '${_runRoot!.path}/window_$passLabel';
        await Directory(outDir).create(recursive: true);
        final windowID = 'k18_pose896_window_$passLabel';
        _log('--- window $passLabel: frames $start..${start + _windowSize - 1} ---');
        _log('  memBeforeInfer=${await _mem()}');

        // Build frames list with imageTensorFloat32ChwPath pointing to the
        // pre-computed official-preprocess .bin (same format Da3NativePreprocessRunner
        // produces in pocketworld_flutter). Plugin reads + assembles MLMultiArray.
        // Pose mode additionally carries raw ARKit w2c extrinsics + processed-scale
        // intrinsics per frame (plugin keys: cameraExtrinsicOpenCvW2c4x4 /
        // cameraIntrinsic3x3), loaded from pose_frames.json.
        final poseFrames = await _loadPoseFrames();
        final frames = <Map<String, Object?>>[];
        for (var slot = 0; slot < _windowSize; slot += 1) {
          final frameIdx = start + slot;
          final tensorPath =
              '${_tensorDir!.path}/${frameIdx.toString().padLeft(6, '0')}.float32_chw.bin';
          final frameID =
              'frame_${frameIdx.toString().padLeft(6, '0')}_window_${passLabel}_slot_${slot.toString().padLeft(3, '0')}';
          final pose = poseFrames[frameIdx];
          frames.add(<String, Object?>{
            'frameID': frameID,
            'frameIndex': slot,
            'imagePath': tensorPath, // dummy — plugin only uses if tensorPath missing
            'imageRelativePath': '$slot.bin',
            'imageTensorFloat32ChwPath': tensorPath,
            'imageTensorFloat32ChwRelativePath': '$slot.bin',
            'sourceImagePath': tensorPath,
            'cameraExtrinsicOpenCvW2c4x4': pose['cameraExtrinsicOpenCvW2c4x4'],
            'cameraIntrinsic3x3': pose['cameraIntrinsic3x3'],
          });
        }

        final t0 = DateTime.now();
        final result = await _channel.invokeMapMethod<String, dynamic>(
          'runDa3DepthWindow',
          <String, Object?>{
            'outputDir': outDir,
            'windowID': windowID,
            'model': <String, Object?>{
              'id': 'DA3-BASE',
              'license': 'Apache-2.0',
              'commercialSafe': true,
              'resourceName': _modelName,
              'windowSize': _windowSize,
              'inputHeight': _inputHeight,
              'inputWidth': _inputWidth,
              'da3InputContract': 'pose_conditioned',
              'officialStreamingBaseline': false,
            },
            'inputSizePolicy': <String, Object?>{
              'locked': true,
              'width': _inputWidth,
              'height': _inputHeight,
            },
            'frames': frames,
          },
        );
        final elapsedMs = DateTime.now().difference(t0).inMilliseconds;
        _log('  result in ${elapsedMs}ms: status=${result?["status"]} memAfter=${await _mem()}');
        if (result == null || result['status'] != 'completed') {
          _log('  ABORT: window failed; full result=$result');
          break;
        }
        summaries.add({
          'window_index': pass,
          'window_start': start,
          'output_dir': outDir,
          'elapsed_ms': elapsedMs,
          ...result,
        });
      }

      final summary = {
        'schemaVersion': 'da3_bench_k18_pose_504x896_window000_v1',
        'model': _modelName,
        'windowSize': _windowSize,
        'overlap': _overlap,
        'stride': _stride,
        'totalFrames': _totalFrames,
        'numChunks': numChunks,
        'runRoot': _runRoot!.path,
        'elapsedMs': stopwatch.elapsedMilliseconds,
        'windows': summaries,
      };
      final summaryFile = File('${_runRoot!.path}/bench_summary.json');
      await summaryFile.writeAsString(
        const JsonEncoder.withIndent('  ').convert(summary),
      );
      _log('=== DONE in ${stopwatch.elapsed} → ${summaryFile.path}');
    } catch (e, st) {
      _log('EXCEPTION: $e');
      _log(st.toString().split('\n').take(8).join('\n'));
    } finally {
      if (mounted) setState(() => _running = false);
    }
  }

  /// Per-frame pose maps from the bundled pose_frames.json (index-aligned).
  Future<List<Map<String, Object?>>> _loadPoseFrames() async {
    final raw = await rootBundle.loadString('$_assetDir/pose_frames.json');
    final decoded = jsonDecode(raw) as Map<String, dynamic>;
    final list = (decoded['frames'] as List<dynamic>)
        .map((e) => (e as Map<String, dynamic>).cast<String, Object?>())
        .toList();
    if (list.length != _totalFrames) {
      throw StateError('pose_frames.json frames=${list.length} expected=$_totalFrames');
    }
    return list;
  }

  Future<void> _prepareTestTensors() async {
    final docs = await getApplicationDocumentsDirectory();
    // Resolution-specific dir — avoids stale bins from other resolutions.
    _tensorDir = Directory('${docs.path}/test_tensors_504x896_n18');
    if (await _tensorDir!.exists()) {
      final n = (await _tensorDir!.list().toList())
          .where((e) => e.path.endsWith('.float32_chw.bin'))
          .length;
      if (n == _totalFrames) {
        _log('test_tensors already prepared ($n bins)');
        return;
      }
      await _tensorDir!.delete(recursive: true);
    }
    await _tensorDir!.create(recursive: true);
    _log('copying $_totalFrames fp32 CHW tensor bins from rootBundle to ${_tensorDir!.path}');
    final t0 = DateTime.now();
    for (var i = 0; i < _totalFrames; i += 1) {
      final filename = '${i.toString().padLeft(6, '0')}.float32_chw.bin';
      final data = await rootBundle.load('$_assetDir/$filename');
      final bytes = data.buffer.asUint8List(
        data.offsetInBytes,
        data.lengthInBytes,
      );
      if (bytes.length != _perFrameBytes) {
        throw StateError('tensor $filename size=${bytes.length} expected=$_perFrameBytes');
      }
      await File('${_tensorDir!.path}/$filename').writeAsBytes(bytes, flush: true);
      if (i % 50 == 0) _log('  copied $i/$_totalFrames');
    }
    _log('copy done in ${DateTime.now().difference(t0).inSeconds}s');
  }

  /// Load 90 pre-computed fp32 CHW tensor bins starting from [start] and
  /// memcpy them into a [1, K, 3, H, W] Float32List batch.
  ///
  /// Each bin is exactly _perFrameBytes (3*280*504*4 = 1,693,440) bytes of
  /// little-endian fp32 in CHW layout (R[0..plane], G[plane..2*plane],
  /// B[2*plane..3*plane]) produced by aether_cpp/da3_preprocess
  /// (upper_bound_resize + ImageNet z-score), bit-identical to Mac PyTorch.
  Future<Float32List> _loadBatch(int start) async {
    final batch = Float32List(
      1 * _windowSize * 3 * _inputHeight * _inputWidth,
    );
    final batchBytes = batch.buffer.asUint8List();
    for (var slot = 0; slot < _windowSize; slot += 1) {
      final frameIdx = start + slot;
      final filename = '${frameIdx.toString().padLeft(6, '0')}.float32_chw.bin';
      final file = File('${_tensorDir!.path}/$filename');
      final bytes = await file.readAsBytes();
      if (bytes.length != _perFrameBytes) {
        throw StateError('tensor $filename size=${bytes.length} expected=$_perFrameBytes');
      }
      batchBytes.setRange(
        slot * _perFrameBytes,
        (slot + 1) * _perFrameBytes,
        bytes,
      );
    }
    return batch;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('DA3 K90 414f Bench'),
        actions: [
          if (_running)
            const Padding(
              padding: EdgeInsets.all(16),
              child: SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2.0),
              ),
            )
          else
            IconButton(
              icon: const Icon(Icons.play_arrow),
              onPressed: () => unawaited(_runBench()),
            ),
        ],
      ),
      body: ListView.builder(
        controller: _scroll,
        padding: const EdgeInsets.all(12),
        itemCount: _logs.length,
        itemBuilder: (_, i) => Padding(
          padding: const EdgeInsets.only(bottom: 4),
          child: Text(
            _logs[i],
            style: const TextStyle(fontFamily: 'Menlo', fontSize: 12, height: 1.35),
          ),
        ),
      ),
    );
  }
}
