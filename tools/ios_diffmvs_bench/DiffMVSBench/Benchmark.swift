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

    /// Find a model in the bundle: prefer real DiffMVS, fall back to placeholder.
    static func locateModel() -> URL? {
        let names = ["DiffMVS", "DiffMVS_PLACEHOLDER"]
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

    static func run(frames: Int, computeUnits: MLComputeUnits, warmup: Int = 5) -> BenchResult {
        var r = BenchResult()
        r.frames = frames
        switch computeUnits {
        case .all: r.computeUnits = "ALL (ANE+GPU+CPU)"
        case .cpuAndGPU: r.computeUnits = "CPU+GPU"
        case .cpuAndNeuralEngine: r.computeUnits = "CPU+ANE"
        default: r.computeUnits = "CPU only"
        }
        guard let url = locateModel() else {
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
            let t0 = CFAbsoluteTimeGetCurrent()
            for _ in 0..<frames {
                let s = CFAbsoluteTimeGetCurrent()
                _ = try model.prediction(from: provider)
                times.append((CFAbsoluteTimeGetCurrent() - s) * 1000.0)
                peak = max(peak, physFootprintMB())
            }
            r.totalSec = CFAbsoluteTimeGetCurrent() - t0
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
