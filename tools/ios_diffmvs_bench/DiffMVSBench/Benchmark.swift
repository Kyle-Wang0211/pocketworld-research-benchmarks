import Foundation
import CoreML

/// Model-agnostic CoreML benchmark. Loads a .mlpackage/.mlmodelc from the bundle,
/// auto-builds random inputs from the model's own input descriptions, runs a warmup
/// then N timed predictions, and reports per-frame latency + PEAK phys_footprint
/// (the exact memory figure iOS Jetsam uses against the ~4.1GB budget).
struct BenchResult {
    var ok = false
    var message = ""
    var computeUnits = ""
    var frames = 0
    var medianMs = 0.0
    var p90Ms = 0.0
    var minMs = 0.0
    var totalSec = 0.0
    var baselineMB = 0.0
    var peakMB = 0.0
    var inputSummary = ""
    // Device-normalized process CPU% DURING the timed inference loop (busy% of the
    // whole device's logical cores). 100 - meanCpuNorm ≈ CPU headroom left for a
    // concurrent CPU fusion stage — the on-device GPU-CPU-overlap headroom signal.
    var cpuMeanNorm = 0.0
    var cpuPeakNorm = 0.0
    var cpuSamples = 0
    var logicalCores = 0
}

/// Samples this process's CPU usage every 50ms on a background timer (verbatim
/// pattern from Da3DepthPlugin.CpuSampler). One-core% = 100 per fully-busy core;
/// device-normalized% divides by logical core count. TH_FLAGS_IDLE threads excluded.
fileprivate final class CpuMonitor {
    private let queue = DispatchQueue(label: "pocketworld.diffmvs.cpu_sampler")
    private var timer: DispatchSourceTimer?
    private var samples: [Double] = []

    static func processCpuOneCorePercent() -> Double {
        var threadList: thread_act_array_t?
        var threadCount = mach_msg_type_number_t(0)
        guard task_threads(mach_task_self_, &threadList, &threadCount) == KERN_SUCCESS,
              let threadList else { return 0.0 }
        defer {
            vm_deallocate(mach_task_self_, vm_address_t(UInt(bitPattern: threadList)),
                          vm_size_t(Int(threadCount) * MemoryLayout<thread_t>.stride))
        }
        var total = 0.0
        for i in 0..<Int(threadCount) {
            var info = thread_basic_info()
            var count = mach_msg_type_number_t(THREAD_INFO_MAX)
            let ok = withUnsafeMutablePointer(to: &info) { p in
                p.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                    thread_info(threadList[i], thread_flavor_t(THREAD_BASIC_INFO), $0, &count)
                }
            }
            guard ok == KERN_SUCCESS else { continue }
            if (info.flags & TH_FLAGS_IDLE) == 0 {
                total += Double(info.cpu_usage) / Double(TH_USAGE_SCALE) * 100.0
            }
        }
        return total
    }

    func start() {
        queue.sync {
            samples.removeAll(keepingCapacity: true)
            let t = DispatchSource.makeTimerSource(queue: queue)
            t.schedule(deadline: .now(), repeating: .milliseconds(50))
            t.setEventHandler { [weak self] in
                self?.samples.append(CpuMonitor.processCpuOneCorePercent())
            }
            self.timer = t; t.resume()
        }
    }

    /// Returns (meanNorm, peakNorm, count, cores) — norm = device-normalized busy%.
    func stop() -> (Double, Double, Int, Int) {
        queue.sync {
            timer?.cancel(); timer = nil
            let cores = max(1, ProcessInfo.processInfo.processorCount)
            guard !samples.isEmpty else { return (0, 0, 0, cores) }
            let peak = samples.max() ?? 0
            let mean = samples.reduce(0, +) / Double(samples.count)
            return (mean / Double(cores), peak / Double(cores), samples.count, cores)
        }
    }
}

enum Benchmark {

    static func physFootprintMB() -> Double {
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<integer_t>.size)
        let kr = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
            }
        }
        return kr == KERN_SUCCESS ? Double(info.phys_footprint) / 1_048_576.0 : -1
    }

    /// Find a model in the bundle by name(s), first match wins.
    static func locateModel(_ names: [String] = ["DiffMVS", "DiffMVS_PLACEHOLDER"]) -> URL? {
        for n in names {
            if let u = Bundle.main.url(forResource: n, withExtension: "mlmodelc") { return u }
            if let u = Bundle.main.url(forResource: n, withExtension: "mlpackage") { return u }
        }
        return nil
    }

    static func makeRandomInputs(_ desc: MLModelDescription) throws -> (MLFeatureProvider, String) {
        var feats: [String: MLFeatureValue] = [:]
        var summary: [String] = []
        for (name, fd) in desc.inputDescriptionsByName {
            guard let c = fd.multiArrayConstraint else {
                summary.append("\(name)=<non-array, skipped>"); continue
            }
            let arr = try MLMultiArray(shape: c.shape, dataType: c.dataType)
            let n = arr.count
            switch c.dataType {
            case .float32:
                let p = arr.dataPointer.bindMemory(to: Float32.self, capacity: n)
                for i in 0..<n { p[i] = Float32.random(in: 0...1) }
            case .float16:
                // fill bytes with a mid value pattern; exact values don't affect timing
                memset(arr.dataPointer, 0x3C, n * 2) // ~1.0 in fp16-ish; timing only
            case .double:
                let p = arr.dataPointer.bindMemory(to: Double.self, capacity: n)
                for i in 0..<n { p[i] = Double.random(in: 0...1) }
            case .int32:
                let p = arr.dataPointer.bindMemory(to: Int32.self, capacity: n)
                for i in 0..<n { p[i] = 0 }
            @unknown default: break
            }
            feats[name] = MLFeatureValue(multiArray: arr)
            summary.append("\(name)\(c.shape.map{$0.intValue})")
        }
        return (try MLDictionaryFeatureProvider(dictionary: feats), summary.joined(separator: " "))
    }

    static func run(frames: Int, computeUnits: MLComputeUnits, warmup: Int = 5,
                    modelNames: [String] = ["DiffMVS", "DiffMVS_PLACEHOLDER"]) -> BenchResult {
        var r = BenchResult()
        r.frames = frames
        switch computeUnits {
        case .all: r.computeUnits = "ALL (ANE+GPU+CPU)"
        case .cpuAndGPU: r.computeUnits = "CPU+GPU"
        case .cpuAndNeuralEngine: r.computeUnits = "CPU+ANE"
        default: r.computeUnits = "CPU only"
        }
        guard let url = locateModel(modelNames) else {
            r.message = "No model found. Add DiffMVS.mlpackage (or the placeholder) to the app target."
            return r
        }
        do {
            // compile if needed
            var compiled = url
            if url.pathExtension == "mlpackage" {
                compiled = try MLModel.compileModel(at: url)
            }
            let cfg = MLModelConfiguration()
            cfg.computeUnits = computeUnits
            let model = try MLModel(contentsOf: compiled, configuration: cfg)
            let (provider, summary) = try makeRandomInputs(model.modelDescription)
            r.inputSummary = summary

            r.baselineMB = physFootprintMB()
            for _ in 0..<warmup { _ = try model.prediction(from: provider) }

            var times: [Double] = []
            var peak = physFootprintMB()
            let mon = CpuMonitor(); mon.start()          // sample CPU busy% during inference
            let t0 = CFAbsoluteTimeGetCurrent()
            for _ in 0..<frames {
                let s = CFAbsoluteTimeGetCurrent()
                _ = try model.prediction(from: provider)
                times.append((CFAbsoluteTimeGetCurrent() - s) * 1000.0)
                peak = max(peak, physFootprintMB())
            }
            r.totalSec = CFAbsoluteTimeGetCurrent() - t0
            let (cpuMean, cpuPeak, cpuN, cores) = mon.stop()
            r.cpuMeanNorm = cpuMean; r.cpuPeakNorm = cpuPeak
            r.cpuSamples = cpuN; r.logicalCores = cores
            times.sort()
            r.minMs = times.first ?? 0
            r.medianMs = times[times.count / 2]
            r.p90Ms = times[Int(Double(times.count) * 0.9)]
            r.peakMB = peak
            r.ok = true
            r.message = url.lastPathComponent.contains("PLACEHOLDER")
                ? "⚠️ PLACEHOLDER model — plumbing check only, NOT real DiffMVS timing."
                : "Real DiffMVS model."
        } catch {
            r.message = "Failed: \(error.localizedDescription)"
        }
        return r
    }
}
