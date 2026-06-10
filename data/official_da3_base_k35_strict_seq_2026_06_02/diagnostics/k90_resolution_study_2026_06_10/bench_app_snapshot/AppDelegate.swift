import Flutter
import UIKit
import Darwin
import CoreML
import Accelerate
#if canImport(os)
import os
#endif

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {

  // Cached compiled model (.mlmodelc URL) to avoid repeated compilation
  private static var compiledModelURL: URL?
  private static var loadedModel: MLModel?
  private static var loadedModelName: String?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    let registrar = engineBridge.pluginRegistry.registrar(forPlugin: "PocketWorldDa3Bench")!

    // mem channel — RSS + jetsam-available bytes
    let memChannel = FlutterMethodChannel(
      name: "da3_bench/mem", binaryMessenger: registrar.messenger())
    memChannel.setMethodCallHandler { (call, result) in
      switch call.method {
      case "snapshot":
        result([
          "rss_mb": AppDelegate.residentMB(),
          "jetsam_avail_mb": AppDelegate.jetsamAvailMB(),
        ])
      default: result(FlutterMethodNotImplemented)
      }
    }

    // Use proven-working pocketworld_flutter Da3DepthPlugin verbatim. Registers
    // channel "pocketworld/da3_depth" with method "runDa3DepthWindow".
    Da3DepthPlugin.register(with: registrar.messenger())

    // coreml channel — load + run multi-view DA3 mlpackage
    let mlChannel = FlutterMethodChannel(
      name: "da3_bench/coreml", binaryMessenger: registrar.messenger())
    mlChannel.setMethodCallHandler { (call, result) in
      switch call.method {
      case "load_model":
        let args = call.arguments as? [String: Any] ?? [:]
        let k = AppDelegate.parseK(args)
        let side = AppDelegate.parseSide(args)
        let height = AppDelegate.parseHeight(args, fallback: side)
        let width = AppDelegate.parseWidth(args, fallback: side)
        let mode = AppDelegate.parseMode(args)
        DispatchQueue.global(qos: .userInitiated).async {
          AppDelegate.loadModel(mode: mode, k: k, side: side, height: height, width: width, result: result)
        }
      case "run_inference":
        // CRITICAL: Data(typedData.data) is COW — shares NSData backing buffer.
        // When Flutter releases typedData, shared buffer dies → EXC_BAD_ACCESS
        // in bg thread (caught K=5 spike).
        // Fix: build MLMultiArray SYNCHRONOUSLY on this thread (memcpy original
        // buffer). MLMultiArray owns its memory → safe to pass to bg thread.
        let args = call.arguments as? [String: Any] ?? [:]
        guard let typedData = args["image"] as? FlutterStandardTypedData else {
          result(FlutterError(code: "BAD_INPUT", message: "image bytes required", details: nil))
          return
        }
        let k = AppDelegate.parseK(args)
        let side = AppDelegate.parseSide(args)
        let height = AppDelegate.parseHeight(args, fallback: side)
        let width = AppDelegate.parseWidth(args, fallback: side)
        let mode = AppDelegate.parseMode(args)
        let skipOutputStats = AppDelegate.parseBool(args, key: "skip_output_stats", fallback: false)
        guard AppDelegate.modelName(mode: mode, k: k, side: side, height: height, width: width) != nil else {
          result(FlutterError(code: "BAD_CONFIG", message: AppDelegate.supportedConfigMessage(), details: nil))
          return
        }
        let bytes = typedData.data
        let expectedBytes = 1 * k * 3 * height * width * 4
        guard bytes.count == expectedBytes else {
          result(FlutterError(code: "BAD_SIZE",
            message: "expected \(expectedBytes) bytes got \(bytes.count)", details: nil))
          return
        }
        let shape: [NSNumber] = [
          NSNumber(value: 1), NSNumber(value: k), NSNumber(value: 3),
          NSNumber(value: height), NSNumber(value: width)
        ]
        let arr: MLMultiArray
        do {
          arr = try MLMultiArray(shape: shape, dataType: .float32)
          bytes.withUnsafeBytes { src in
            arr.dataPointer.copyMemory(from: src.baseAddress!, byteCount: expectedBytes)
          }
        } catch {
          result(FlutterError(code: "MLARRAY_FAILED", message: "\(error)", details: nil))
          return
        }
        // arr now owns its own memory copy, safe to capture in async closure
        DispatchQueue.global(qos: .userInitiated).async {
          AppDelegate.runInferenceWithArray(arr: arr, k: k, side: side, height: height, width: width, skipOutputStats: skipOutputStats, result: result)
        }
      case "run_window_save":
        // K=90 image-only: takes batch bytes + saves 4 output tensors to disk.
        let args = call.arguments as? [String: Any] ?? [:]
        guard let typedData = args["image"] as? FlutterStandardTypedData else {
          result(FlutterError(code: "BAD_INPUT", message: "image bytes required", details: nil))
          return
        }
        let k = AppDelegate.parseK(args)
        let height = AppDelegate.parseHeight(args, fallback: 280)
        let width = AppDelegate.parseWidth(args, fallback: 504)
        guard let outDir = args["output_dir"] as? String else {
          result(FlutterError(code: "BAD_INPUT", message: "output_dir required", details: nil))
          return
        }
        let windowIndex = (args["window_index"] as? Int) ?? 0
        let windowStart = (args["window_start_frame"] as? Int) ?? 0
        let bytes = typedData.data
        let expectedBytes = 1 * k * 3 * height * width * 4
        guard bytes.count == expectedBytes else {
          result(FlutterError(code: "BAD_SIZE",
            message: "expected \(expectedBytes) bytes got \(bytes.count)", details: nil))
          return
        }
        let shape: [NSNumber] = [
          NSNumber(value: 1), NSNumber(value: k), NSNumber(value: 3),
          NSNumber(value: height), NSNumber(value: width)
        ]
        let arr: MLMultiArray
        do {
          arr = try MLMultiArray(shape: shape, dataType: .float32)
          // Use typed Float32 copy (same as Da3DepthPlugin.makeImageArray) instead
          // of raw byte memcpy — BNNSGraph CPU backend is fussy about init mode.
          let totalFloats = 1 * k * 3 * height * width
          let dstPtr = arr.dataPointer.bindMemory(to: Float32.self, capacity: totalFloats)
          bytes.withUnsafeBytes { rawBuffer in
            guard let srcPtr = rawBuffer.bindMemory(to: Float32.self).baseAddress else { return }
            dstPtr.update(from: srcPtr, count: totalFloats)
          }
        } catch {
          result(FlutterError(code: "MLARRAY_FAILED", message: "\(error)", details: nil))
          return
        }
        // Diagnostic: log input tensor stats to verify data is valid before predict
        do {
          let totalFloats = 1 * k * 3 * height * width
          let p = arr.dataPointer.bindMemory(to: Float32.self, capacity: totalFloats)
          let buf = UnsafeBufferPointer(start: p, count: totalFloats)
          var nanCount = 0
          var infCount = 0
          var minV: Float = .greatestFiniteMagnitude
          var maxV: Float = -.greatestFiniteMagnitude
          var sum: Double = 0
          let sampleStride = max(1, totalFloats / 100000)
          var sampleCount = 0
          var i = 0
          while i < totalFloats {
            let v = buf[i]
            if v.isNaN { nanCount += 1 }
            else if v.isInfinite { infCount += 1 }
            else {
              minV = min(minV, v); maxV = max(maxV, v); sum += Double(v); sampleCount += 1
            }
            i += sampleStride
          }
          let mean = sampleCount > 0 ? sum / Double(sampleCount) : 0
          NSLog("[bench] input arr stats k=%d shape=[1,%d,3,%d,%d] nan=%d inf=%d min=%.4f max=%.4f mean=%.4f (sampled %d)",
                k, k, height, width, nanCount, infCount, minV, maxV, mean, sampleCount)
        }
        DispatchQueue.global(qos: .userInitiated).async {
          AppDelegate.runWindowSave(arr: arr, k: k, height: height, width: width,
                                    outDir: outDir, windowIndex: windowIndex,
                                    windowStart: windowStart, result: result)
        }
      case "run_inference_synthetic":
        let args = call.arguments as? [String: Any] ?? [:]
        let k = AppDelegate.parseK(args)
        let side = AppDelegate.parseSide(args)
        let height = AppDelegate.parseHeight(args, fallback: side)
        let width = AppDelegate.parseWidth(args, fallback: side)
        let mode = AppDelegate.parseMode(args)
        let skipOutputStats = AppDelegate.parseBool(args, key: "skip_output_stats", fallback: false)
        guard AppDelegate.modelName(mode: mode, k: k, side: side, height: height, width: width) != nil else {
          result(FlutterError(code: "BAD_CONFIG", message: AppDelegate.supportedConfigMessage(), details: nil))
          return
        }
        DispatchQueue.global(qos: .userInitiated).async {
          do {
            let arr = try AppDelegate.makeSyntheticImage(k: k, height: height, width: width)
            AppDelegate.runInferenceWithArray(arr: arr, k: k, side: side, height: height, width: width, skipOutputStats: skipOutputStats, result: result)
          } catch {
            result(FlutterError(code: "MLARRAY_FAILED", message: "\(error)", details: nil))
          }
        }
      default: result(FlutterMethodNotImplemented)
      }
    }
  }

  private static func residentMB() -> Double {
    var info = mach_task_basic_info()
    var count = mach_msg_type_number_t(
      MemoryLayout<mach_task_basic_info>.size / MemoryLayout<integer_t>.size)
    let kerr: kern_return_t = withUnsafeMutablePointer(to: &info) {
      $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
        task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
      }
    }
    guard kerr == KERN_SUCCESS else { return -1.0 }
    return Double(info.resident_size) / 1024.0 / 1024.0
  }

  private static func jetsamAvailMB() -> Double {
    return Double(os_proc_available_memory()) / 1024.0 / 1024.0
  }

  private static func modelName(mode: String, k: Int, side: Int, height: Int, width: Int) -> String? {
    if mode == "image_only" {
      switch (k, height, width) {
      case (60, 280, 504): return "DA3BASE_280x504_N60_image_only"
      case (90, 280, 504): return "DA3BASE_280x504_N90_image_only"
      default: return nil
      }
    }
    if mode == "pose" || mode == "pose_conditioned" {
      switch (k, height, width) {
      case (30, 504, 896): return "DA3BASE_504x896_N30_pose"
      case (30, 588, 1036): return "DA3BASE_588x1036_N30_pose"
      case (35, 434, 770): return "DA3BASE_434x770_N35_pose"
      case (35, 448, 756): return "DA3BASE_448x756_N35_pose"
      case (35, 462, 756): return "DA3BASE_462x756_N35_pose"
      case (35, 476, 742): return "DA3BASE_476x742_N35_pose"
      case (35, 448, 770): return "DA3BASE_448x770_N35_pose"
      case (35, 448, 798): return "DA3BASE_448x798_N35_pose"
      case (40, 448, 896): return "DA3BASE_448x896_N40_pose"
      case (40, 504, 896): return "DA3BASE_504x896_N40_pose"
      default: return nil
      }
    }
    return nil
  }

  private static func supportedConfigMessage() -> String {
    return "supported configs: mode=pose K=30 504x896, K=30 588x1036, K=35 434x770, K=35 448x756, K=35 462x756, K=35 476x742, K=35 448x770, K=35 448x798, K=40 448x896, K=40 504x896"
  }

  private static func parseK(_ args: [String: Any]) -> Int {
    if let k = args["k"] as? Int { return k }
    if let n = args["k"] as? NSNumber { return n.intValue }
    return 4
  }

  private static func parseSide(_ args: [String: Any]) -> Int {
    if let side = args["side"] as? Int { return side }
    if let n = args["side"] as? NSNumber { return n.intValue }
    return 252
  }

  private static func parseHeight(_ args: [String: Any], fallback: Int) -> Int {
    if let height = args["height"] as? Int { return height }
    if let n = args["height"] as? NSNumber { return n.intValue }
    return fallback
  }

  private static func parseWidth(_ args: [String: Any], fallback: Int) -> Int {
    if let width = args["width"] as? Int { return width }
    if let n = args["width"] as? NSNumber { return n.intValue }
    return fallback
  }

  private static func parseMode(_ args: [String: Any]) -> String {
    if let mode = args["mode"] as? String { return mode.lowercased() }
    return "multiview"
  }

  private static func parseBool(_ args: [String: Any], key: String, fallback: Bool) -> Bool {
    if let value = args[key] as? Bool { return value }
    if let value = args[key] as? NSNumber { return value.boolValue }
    if let value = args[key] as? String {
      return ["1", "true", "yes", "y"].contains(value.lowercased())
    }
    return fallback
  }

  /// Load + compile the mlpackage from app bundle. Caches compiled URL + MLModel.
  private static func loadModel(mode: String, k: Int, side: Int, height: Int, width: Int, result: @escaping FlutterResult) {
    let memBefore = residentMB()
    let availBefore = jetsamAvailMB()
    NSLog("[CoreML] load_model start: rss=%.0f MB, jetsam_avail=%.0f MB", memBefore, availBefore)

    // Xcode auto-compiles .mlpackage to .mlmodelc at build time.
    // Try both extensions; also list bundle for diagnostics if neither found.
    guard let modelName = modelName(mode: mode, k: k, side: side, height: height, width: width) else {
      result(FlutterError(code: "BAD_CONFIG", message: supportedConfigMessage(), details: nil))
      return
    }
    if loadedModelName != modelName {
      compiledModelURL = nil
      loadedModel = nil
    }
    var resolvedURL: URL?
    for ext in ["mlmodelc", "mlpackage"] {
      if let url = Bundle.main.url(forResource: modelName, withExtension: ext) {
        resolvedURL = url
        NSLog("[CoreML] found %@.%@ at: %@", modelName, ext, url.path)
        break
      }
    }
    guard let mlpackageURL = resolvedURL else {
      // Diagnostics: list all Bundle.main resources
      let bundleURL = Bundle.main.bundleURL
      var bundleListing: [String] = []
      if let enumerator = FileManager.default.enumerator(atPath: bundleURL.path) {
        for case let path as String in enumerator {
          if path.contains("DA3") || path.hasSuffix(".mlmodelc") || path.hasSuffix(".mlpackage") {
            bundleListing.append(path)
          }
        }
      }
      let listingStr = bundleListing.isEmpty ? "(no DA3/.mlmodelc/.mlpackage found)" :
                                                bundleListing.joined(separator: ", ")
      NSLog("[CoreML] model NOT FOUND. Bundle DA3 listing: \(listingStr)")
      result(FlutterError(code: "NOT_FOUND",
                          message: "\(modelName).mlmodelc/.mlpackage not in bundle. " +
                                   "Bundle DA3 contents: \(listingStr)",
                          details: nil))
      return
    }

    do {
      let tCompile = CFAbsoluteTimeGetCurrent()
      let compiledURL: URL
      if let cached = compiledModelURL {
        compiledURL = cached
        NSLog("[CoreML] using cached compiled .mlmodelc")
      } else if mlpackageURL.pathExtension == "mlmodelc" {
        // Already compiled (Xcode did it at build time) — use directly
        compiledURL = mlpackageURL
        compiledModelURL = compiledURL
        NSLog("[CoreML] using bundled .mlmodelc directly (no runtime compile needed)")
      } else {
        compiledURL = try MLModel.compileModel(at: mlpackageURL)
        compiledModelURL = compiledURL
        NSLog("[CoreML] compileModel (.mlpackage→.mlmodelc) done in %.0f ms",
              (CFAbsoluteTimeGetCurrent() - tCompile) * 1000)
      }
      let memAfterCompile = residentMB()
      NSLog("[CoreML] after compile: rss=%.0f MB (Δ%.0f)", memAfterCompile, memAfterCompile - memBefore)

      // Production pocketworld_flutter SinglePassWrapper.swift:103 uses .cpuOnly.
      // ANE 256MB cache can't host 410M params; GPU 5D cross-attention OOMs.
      // CPU is slower but has full app-budget RAM (~3 GB on iPhone 14 Pro).
      let config = MLModelConfiguration()
      config.computeUnits = .cpuAndGPU  // try GPU path to bypass BNNSGraph CPU backend issue
      let tLoad = CFAbsoluteTimeGetCurrent()
      NSLog("[CoreML] loading with computeUnits=cpuAndGPU (debug: bypass BNNSGraph)")
      let model = try MLModel(contentsOf: compiledURL, configuration: config)
      NSLog("[CoreML] ✓ loaded with cpuOnly")
      loadedModel = model
      loadedModelName = modelName
      let loadMs = (CFAbsoluteTimeGetCurrent() - tLoad) * 1000
      let memAfterLoad = residentMB()
      let availAfterLoad = jetsamAvailMB()
      NSLog("[CoreML] MLModel loaded in %.0f ms: rss=%.0f MB (Δ%.0f), jetsam_avail=%.0f MB",
            loadMs, memAfterLoad, memAfterLoad - memAfterCompile, availAfterLoad)

      result([
        "compile_ms": (CFAbsoluteTimeGetCurrent() - tCompile) * 1000,
        "load_ms": loadMs,
        "rss_before_mb": memBefore,
        "rss_after_compile_mb": memAfterCompile,
        "rss_after_load_mb": memAfterLoad,
        "jetsam_avail_before_mb": availBefore,
        "jetsam_avail_after_load_mb": availAfterLoad,
        "mlpackage_path": mlpackageURL.path,
        "compiled_path": compiledURL.path,
        "model_name": modelName,
      ])
    } catch {
      NSLog("[CoreML] load FAILED: \(error)")
      result(FlutterError(code: "LOAD_FAILED",
                          message: "\(error)", details: nil))
    }
  }

  /// Run inference with pre-built MLMultiArray (built on caller's thread).
  /// MLMultiArray owns its memory, safe to pass across threads.
  private static func runInferenceWithArray(arr: MLMultiArray, k: Int, side: Int, height: Int, width: Int, skipOutputStats: Bool, result: @escaping FlutterResult) {
    guard let model = loadedModel else {
      result(FlutterError(code: "NO_MODEL", message: "call load_model first", details: nil))
      return
    }

    let memBefore = residentMB()
    let availBefore = jetsamAvailMB()
    NSLog("[CoreML] inference start: rss=%.0f MB, jetsam_avail=%.0f MB", memBefore, availBefore)

    do {
      let memAfterInput = memBefore  // arr already built on caller thread
      NSLog("[CoreML] mlarr already built (caller thread), shape=%@", arr.shape.description)

      var inputs: [String: MLFeatureValue] = ["image": MLFeatureValue(multiArray: arr)]
      if (loadedModelName ?? "").contains("_pose") {
        inputs["extrinsics"] = MLFeatureValue(multiArray: try makeSyntheticExtrinsics(k: k))
        inputs["intrinsics"] = MLFeatureValue(multiArray: try makeSyntheticIntrinsics(k: k, height: height, width: width))
      }
      let provider = try MLDictionaryFeatureProvider(dictionary: inputs)
      let cpuSampler = CPUUsageSampler()
      cpuSampler.start()
      let tInf = CFAbsoluteTimeGetCurrent()
      let output = try model.prediction(from: provider)
      let inferMs = (CFAbsoluteTimeGetCurrent() - tInf) * 1000
      let cpuStats = cpuSampler.stop()
      let memPeak = residentMB()
      let availAfter = jetsamAvailMB()
      NSLog("[CoreML] inference done in %.0f ms: peak rss=%.0f MB (Δ%.0f), jetsam_avail=%.0f MB",
            inferMs, memPeak, memPeak - memAfterInput, availAfter)
      NSLog("[CoreML] cpu peak/mean one-core: %.0f%% / %.0f%% (%d samples); device-normalized: %.1f%% / %.1f%% over %d logical cores",
            cpuStats.peakOneCorePercent, cpuStats.meanOneCorePercent, cpuStats.sampleCount,
            cpuStats.peakDevicePercent, cpuStats.meanDevicePercent, cpuStats.logicalCores)

      if skipOutputStats {
        result([
          "infer_ms": inferMs,
          "model_name": loadedModelName ?? "",
          "rss_before_mb": memBefore,
          "rss_after_input_mb": memAfterInput,
          "rss_peak_mb": memPeak,
          "jetsam_avail_before_mb": availBefore,
          "jetsam_avail_after_mb": availAfter,
          "cpu_sample_count": cpuStats.sampleCount,
          "cpu_peak_one_core_percent": cpuStats.peakOneCorePercent,
          "cpu_mean_one_core_percent": cpuStats.meanOneCorePercent,
          "cpu_peak_device_percent": cpuStats.peakDevicePercent,
          "cpu_mean_device_percent": cpuStats.meanDevicePercent,
          "cpu_logical_cores": cpuStats.logicalCores,
          "output_stats_skipped": true,
        ])
        return
      }

      // Extract depth + depth_conf shapes/stats for sanity
      guard let depthArr = output.featureValue(for: "depth")?.multiArrayValue,
            let confArr = output.featureValue(for: "depth_conf")?.multiArrayValue else {
        result(FlutterError(code: "OUTPUT_MISSING",
          message: "depth/depth_conf not in output (have: \(output.featureNames))", details: nil))
        return
      }

      let depthValues = try multiArrayToFloatBuffer(depthArr)
      let confValues = try multiArrayToFloatBuffer(confArr)
      let depthStats = stats(depthValues)
      let confStats = stats(confValues)

      var response: [String: Any] = [
        "infer_ms": inferMs,
        "model_name": loadedModelName ?? "",
        "rss_before_mb": memBefore,
        "rss_after_input_mb": memAfterInput,
        "rss_peak_mb": memPeak,
        "jetsam_avail_before_mb": availBefore,
        "jetsam_avail_after_mb": availAfter,
        "cpu_sample_count": cpuStats.sampleCount,
        "cpu_peak_one_core_percent": cpuStats.peakOneCorePercent,
        "cpu_mean_one_core_percent": cpuStats.meanOneCorePercent,
        "cpu_peak_device_percent": cpuStats.peakDevicePercent,
        "cpu_mean_device_percent": cpuStats.meanDevicePercent,
        "cpu_logical_cores": cpuStats.logicalCores,
        "depth_shape": depthArr.shape.map { $0.intValue },
        "conf_shape": confArr.shape.map { $0.intValue },
        "depth_dtype": "\(depthArr.dataType)",
        "conf_dtype": "\(confArr.dataType)",
        "depth_min": Double(depthStats.min),
        "depth_max": Double(depthStats.max),
        "depth_mean": Double(depthStats.mean),
        "depth_finite_ratio": depthStats.finiteRatio,
        "depth_nan_count": depthStats.nanCount,
        "depth_inf_count": depthStats.infCount,
        "conf_min": Double(confStats.min),
        "conf_max": Double(confStats.max),
        "conf_mean": Double(confStats.mean),
        "conf_finite_ratio": confStats.finiteRatio,
        "conf_nan_count": confStats.nanCount,
        "conf_inf_count": confStats.infCount,
      ]

      if let predExtr = output.featureValue(for: "pred_extrinsics")?.multiArrayValue {
        let values = try multiArrayToFloatBuffer(predExtr)
        let predStats = stats(values)
        response["pred_extrinsics_shape"] = predExtr.shape.map { $0.intValue }
        response["pred_extrinsics_dtype"] = "\(predExtr.dataType)"
        response["pred_extrinsics_finite_ratio"] = predStats.finiteRatio
        response["pred_extrinsics_nan_count"] = predStats.nanCount
        response["pred_extrinsics_inf_count"] = predStats.infCount
      }
      if let predIntr = output.featureValue(for: "pred_intrinsics")?.multiArrayValue {
        let values = try multiArrayToFloatBuffer(predIntr)
        let predStats = stats(values)
        response["pred_intrinsics_shape"] = predIntr.shape.map { $0.intValue }
        response["pred_intrinsics_dtype"] = "\(predIntr.dataType)"
        response["pred_intrinsics_finite_ratio"] = predStats.finiteRatio
        response["pred_intrinsics_nan_count"] = predStats.nanCount
        response["pred_intrinsics_inf_count"] = predStats.infCount
      }

      result(response)
    } catch {
      NSLog("[CoreML] inference FAILED: \(error)")
      result(FlutterError(code: "INFER_FAILED",
                          message: "\(error)", details: nil))
    }
  }

  private struct ArrayStats {
    let min: Float
    let max: Float
    let mean: Float
    let finiteRatio: Double
    let nanCount: Int
    let infCount: Int
  }

  private struct CPUUsageStats {
    let sampleCount: Int
    let peakOneCorePercent: Double
    let meanOneCorePercent: Double
    let peakDevicePercent: Double
    let meanDevicePercent: Double
    let logicalCores: Int
  }

  private final class CPUUsageSampler {
    private let queue = DispatchQueue(label: "pocketworld.coreml.cpu_sampler", qos: .userInitiated)
    private let lock = NSLock()
    private var timer: DispatchSourceTimer?
    private var samples: [Double] = []

    func start() {
      let timer = DispatchSource.makeTimerSource(queue: queue)
      timer.schedule(deadline: .now(), repeating: .milliseconds(25), leeway: .milliseconds(5))
      timer.setEventHandler { [weak self] in
        guard let self else { return }
        let value = AppDelegate.processCPUPercentOneCore()
        guard value >= 0 else { return }
        self.lock.lock()
        self.samples.append(value)
        self.lock.unlock()
      }
      self.timer = timer
      timer.resume()
    }

    func stop() -> CPUUsageStats {
      timer?.cancel()
      timer = nil
      lock.lock()
      let localSamples = samples
      lock.unlock()
      let sampleCount = localSamples.count
      let peak = localSamples.max() ?? -1.0
      let mean = sampleCount > 0 ? localSamples.reduce(0.0, +) / Double(sampleCount) : -1.0
      let cores = max(ProcessInfo.processInfo.processorCount, 1)
      return CPUUsageStats(
        sampleCount: sampleCount,
        peakOneCorePercent: peak,
        meanOneCorePercent: mean,
        peakDevicePercent: peak < 0 ? -1.0 : peak / Double(cores),
        meanDevicePercent: mean < 0 ? -1.0 : mean / Double(cores),
        logicalCores: cores
      )
    }
  }

  private static func processCPUPercentOneCore() -> Double {
    var threads: thread_act_array_t?
    var threadCount = mach_msg_type_number_t(0)
    let kr = task_threads(mach_task_self_, &threads, &threadCount)
    guard kr == KERN_SUCCESS, let threadList = threads else {
      return -1.0
    }
    defer {
      let size = vm_size_t(Int(threadCount) * MemoryLayout<thread_t>.stride)
      vm_deallocate(mach_task_self_, vm_address_t(UInt(bitPattern: threadList)), size)
    }

    var total = 0.0
    for index in 0..<Int(threadCount) {
      var info = thread_basic_info()
      var count = mach_msg_type_number_t(THREAD_INFO_MAX)
      let infoKr: kern_return_t = withUnsafeMutablePointer(to: &info) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
          thread_info(threadList[index], thread_flavor_t(THREAD_BASIC_INFO), $0, &count)
        }
      }
      if infoKr == KERN_SUCCESS && (info.flags & TH_FLAGS_IDLE) == 0 {
        total += Double(info.cpu_usage) / Double(TH_USAGE_SCALE) * 100.0
      }
    }
    return total
  }

  private static func makeSyntheticExtrinsics(k: Int) throws -> MLMultiArray {
    let arr = try MLMultiArray(
      shape: [NSNumber(value: 1), NSNumber(value: k), NSNumber(value: 4), NSNumber(value: 4)],
      dataType: .float32)
    let ptr = arr.dataPointer.bindMemory(to: Float32.self, capacity: arr.count)
    for i in 0..<arr.count { ptr[i] = 0 }
    for v in 0..<k {
      let base = v * 16
      ptr[base + 0] = 1
      ptr[base + 5] = 1
      ptr[base + 10] = 1
      ptr[base + 15] = 1
      let theta = 2.0 * Double.pi * Double(v) / Double(max(k, 1))
      ptr[base + 3] = Float(0.20 * cos(theta))
      ptr[base + 7] = Float(0.16 * sin(theta))
      ptr[base + 11] = Float(0.08 * sin(theta * 1.7))
    }
    return arr
  }

  private static func makeSyntheticIntrinsics(k: Int, height: Int, width: Int) throws -> MLMultiArray {
    let arr = try MLMultiArray(
      shape: [NSNumber(value: 1), NSNumber(value: k), NSNumber(value: 3), NSNumber(value: 3)],
      dataType: .float32)
    let ptr = arr.dataPointer.bindMemory(to: Float32.self, capacity: arr.count)
    for i in 0..<arr.count { ptr[i] = 0 }
    for v in 0..<k {
      let base = v * 9
      ptr[base + 0] = Float(width)
      ptr[base + 4] = Float(height)
      ptr[base + 2] = Float(width) * 0.5
      ptr[base + 5] = Float(height) * 0.5
      ptr[base + 8] = 1
    }
    return arr
  }

  private static func makeSyntheticImage(k: Int, height: Int, width: Int) throws -> MLMultiArray {
    let arr = try MLMultiArray(
      shape: [
        NSNumber(value: 1), NSNumber(value: k), NSNumber(value: 3),
        NSNumber(value: height), NSNumber(value: width)
      ],
      dataType: .float32)
    memset(arr.dataPointer, 0, arr.count * MemoryLayout<Float32>.stride)
    return arr
  }

  private static func multiArrayToFloatBuffer(_ arr: MLMultiArray) throws -> [Float] {
    let count = arr.count
    var out = [Float](repeating: 0, count: count)
    switch arr.dataType.rawValue {
    case 0x10020: // float32
      let ptr = arr.dataPointer.bindMemory(to: Float32.self, capacity: count)
      for i in 0..<count { out[i] = ptr[i] }
    case 0x10010: // float16
      guard #available(iOS 14.0, *) else {
        throw NSError(domain: "CoreMLBench", code: 20,
                      userInfo: [NSLocalizedDescriptionKey: "float16 output needs iOS 14+ conversion"])
      }
      var src = vImage_Buffer(data: arr.dataPointer, height: 1,
                              width: UInt(count), rowBytes: count * 2)
      out.withUnsafeMutableBufferPointer { dst in
        var dest = vImage_Buffer(data: UnsafeMutableRawPointer(dst.baseAddress!),
                                 height: 1, width: UInt(count), rowBytes: count * 4)
        _ = vImageConvert_Planar16FtoPlanarF(&src, &dest, 0)
      }
    case 0x10040: // double
      let ptr = arr.dataPointer.bindMemory(to: Double.self, capacity: count)
      for i in 0..<count { out[i] = Float(ptr[i]) }
    default:
      throw NSError(domain: "CoreMLBench", code: 21,
                    userInfo: [NSLocalizedDescriptionKey: "unsupported MLMultiArray dtype raw=\(arr.dataType.rawValue)"])
    }
    return out
  }

  private static func stats(_ values: [Float]) -> ArrayStats {
    guard !values.isEmpty else {
      return ArrayStats(min: 0, max: 0, mean: 0, finiteRatio: 0, nanCount: 0, infCount: 0)
    }
    var minV = Float.greatestFiniteMagnitude
    var maxV = -Float.greatestFiniteMagnitude
    var sum: Double = 0
    var finiteCount = 0
    var nanCount = 0
    var infCount = 0
    for v in values {
      if v.isNaN {
        nanCount += 1
      } else if v.isInfinite {
        infCount += 1
      } else {
        finiteCount += 1
        minV = min(minV, v)
        maxV = max(maxV, v)
        sum += Double(v)
      }
    }
    guard finiteCount > 0 else {
      return ArrayStats(min: 0, max: 0, mean: 0,
                        finiteRatio: 0, nanCount: nanCount, infCount: infCount)
    }
    return ArrayStats(min: minV, max: maxV, mean: Float(sum / Double(finiteCount)),
                      finiteRatio: Double(finiteCount) / Double(values.count),
                      nanCount: nanCount, infCount: infCount)
  }

  // MARK: - K=90 image-only window save (R1 outputs for Mac R2-R5)

  /// Run prediction on a single K=90 window and save the 4 output tensors
  /// (depth / depth_conf / pred_extrinsics / pred_intrinsics) to outDir as
  /// raw fp32 little-endian binary plus a meta.json with shape info.
  private static func runWindowSave(arr: MLMultiArray, k: Int, height: Int, width: Int,
                                    outDir: String, windowIndex: Int, windowStart: Int,
                                    result: @escaping FlutterResult) {
    guard let model = loadedModel else {
      result(FlutterError(code: "NO_MODEL", message: "call load_model first", details: nil))
      return
    }
    let memBefore = residentMB()
    let availBefore = jetsamAvailMB()
    NSLog("[CoreML] window_save start idx=%d start=%d rss=%.0f MB jetsam=%.0f MB",
          windowIndex, windowStart, memBefore, availBefore)
    do {
      // Diagnostic: dump model description so we know exactly what CoreML expects
      let desc = model.modelDescription
      NSLog("[CoreML] model.inputs:")
      for (name, feat) in desc.inputDescriptionsByName {
        let cstr = feat.multiArrayConstraint
        NSLog("  input %@: type=%@ shape=%@ dtype=%@", name,
              "\(feat.type)", "\(cstr?.shape ?? [])", "\(cstr?.dataType ?? .float32)")
      }
      NSLog("[CoreML] model.outputs:")
      for (name, feat) in desc.outputDescriptionsByName {
        let cstr = feat.multiArrayConstraint
        NSLog("  output %@: type=%@ shape=%@ dtype=%@", name,
              "\(feat.type)", "\(cstr?.shape ?? [])", "\(cstr?.dataType ?? .float32)")
      }
      let provider = try MLDictionaryFeatureProvider(
        dictionary: ["image": MLFeatureValue(multiArray: arr)])
      let cpuSampler = CPUUsageSampler()
      cpuSampler.start()
      let tInf = CFAbsoluteTimeGetCurrent()
      let output = try model.prediction(from: provider)
      let inferMs = (CFAbsoluteTimeGetCurrent() - tInf) * 1000
      let cpuStats = cpuSampler.stop()
      let memPeak = residentMB()
      let availAfter = jetsamAvailMB()
      NSLog("[CoreML] window_save inferred in %.0f ms peak=%.0f MB jetsam=%.0f MB",
            inferMs, memPeak, availAfter)

      let names = ["depth", "depth_conf", "pred_extrinsics", "pred_intrinsics"]
      var savedShapes: [String: [Int]] = [:]
      var savedDtypes: [String: String] = [:]
      var savedFiles: [String: String] = [:]
      for name in names {
        guard let val = output.featureValue(for: name)?.multiArrayValue else {
          NSLog("[CoreML] WARN output %@ not present (have %@)", name, output.featureNames.description)
          continue
        }
        let shape = val.shape.map { $0.intValue }
        let dtype = "\(val.dataType)"
        // Convert to fp32 float buffer regardless of model output dtype.
        let buf = try multiArrayToFloatBuffer(val)
        let bytes = buf.withUnsafeBufferPointer { ptr in
          Data(buffer: ptr)
        }
        let fileURL = URL(fileURLWithPath: outDir).appendingPathComponent("\(name).bin")
        try bytes.write(to: fileURL)
        savedShapes[name] = shape
        savedDtypes[name] = dtype
        savedFiles[name] = fileURL.path
      }

      let meta: [String: Any] = [
        "window_index": windowIndex,
        "window_start_frame": windowStart,
        "window_size": k,
        "input_height": height,
        "input_width": width,
        "model_name": loadedModelName ?? "",
        "infer_ms": inferMs,
        "rss_before_mb": memBefore,
        "rss_peak_mb": memPeak,
        "jetsam_avail_before_mb": availBefore,
        "jetsam_avail_after_mb": availAfter,
        "cpu_peak_one_core_percent": cpuStats.peakOneCorePercent,
        "cpu_mean_one_core_percent": cpuStats.meanOneCorePercent,
        "cpu_peak_device_percent": cpuStats.peakDevicePercent,
        "cpu_mean_device_percent": cpuStats.meanDevicePercent,
        "tensor_shapes": savedShapes,
        "tensor_dtypes": savedDtypes,
        "tensor_files": savedFiles,
        "output_feature_names": output.featureNames.sorted(),
      ]
      let metaURL = URL(fileURLWithPath: outDir).appendingPathComponent("meta.json")
      let metaData = try JSONSerialization.data(withJSONObject: meta,
                                                 options: [.prettyPrinted])
      try metaData.write(to: metaURL)
      NSLog("[CoreML] window_save wrote meta+%d tensors to %@", savedFiles.count, outDir)

      result(meta)
    } catch {
      NSLog("[CoreML] window_save FAILED: %@", "\(error)")
      result(FlutterError(code: "WINDOW_SAVE_FAILED", message: "\(error)", details: nil))
    }
  }
}
