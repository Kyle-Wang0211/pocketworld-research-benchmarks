import Foundation
import CoreML
import UIKit
import os   // os_proc_available_memory

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
    // Thermal context + within-run throttle drift. A resolution sweep heat-soaks the
    // device, so a later (bigger) model can look slow for thermal reasons rather than
    // pixel-count reasons; first10 vs last10 exposes that inside a single run.
    var thermalBefore = ""
    var thermalAfter = ""
    var first10MedianMs = 0.0
    var last10MedianMs = 0.0
    var compileSec = 0.0
    var loadSec = 0.0
    // 被前后台切换/中断污染而作废的帧数(不进任何统计),以及总共发起了多少次预测。
    var discardedFrames = 0
    var attempts = 0
    // 实测预算:baselineAvail = 开跑前离 jetsam 还剩多少;minAvail = 全程最低点。
    // peakMB + minAvail ≈ 系统给本 app 的真实上限。
    var baselineAvailMB = 0.0
    var minAvailMB = 0.0
    var budgetMB = 0.0
}

/// 前后台切换哨兵。
///
/// 计时用的是墙钟,而 app 被挂起时墙钟照走 —— 用户切走 3 分钟,横跨那次挂起的
/// 那一帧就会被记成 180000ms。这不是"一个偏大的测量值",而是**根本不是一次测量**,
/// 混进中位数/p90 里就是污染。
///
/// 所以这里精确标注每一帧是否横跨过一次中断:每收到一次 resignActive/enterBackground
/// 就把 epoch 加一,跑测循环比对帧前帧后的 epoch,不一致就整帧作废并补跑。
/// 用 resignActive 而不只是 enterBackground,是为了连下拉通知中心、来电、
/// 控制中心这类"没真进后台但已经被抢走"的中断一起接住。
fileprivate final class SuspensionSentinel {
    private let lock = NSLock()
    private var _epoch = 0
    private var observers: [NSObjectProtocol] = []

    init() {
        let nc = NotificationCenter.default
        for n in [UIApplication.willResignActiveNotification,
                  UIApplication.didEnterBackgroundNotification] {
            observers.append(nc.addObserver(forName: n, object: nil, queue: nil) { [weak self] _ in
                guard let self else { return }
                self.lock.lock(); self._epoch += 1; self.lock.unlock()
            })
        }
    }

    deinit { observers.forEach { NotificationCenter.default.removeObserver($0) } }

    var epoch: Int { lock.lock(); defer { lock.unlock() }; return _epoch }
}

func thermalStateName(_ s: ProcessInfo.ThermalState) -> String {
    switch s {
    case .nominal: return "nominal"
    case .fair: return "fair"
    case .serious: return "serious"
    case .critical: return "critical"
    @unknown default: return "unknown"
    }
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

    /// 距离 jetsam 还剩多少 MB(os_proc_available_memory)。
    /// phys_footprint + 这个值 ≈ 系统实际给本 app 的内存上限 —— 于是"预算是不是
    /// 真的 4.1GB"变成一个**当场测出来的数**,而不是一个假设。也用它验证
    /// increased-memory-limit 权限有没有真的生效(没生效会明显低一截)。
    static func availableMemMB() -> Double {
        Double(os_proc_available_memory()) / 1_048_576.0
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

    /// 进度探针。phase 取值: locate / compile / load / makeInputs / warmup / timing / done。
    /// 每一帧都回调一次(单帧是秒级,写盘开销可以忽略),所以拉一次心跳文件就能知道
    /// "现在在哪一档、哪个阶段、第几帧、当前峰值多少" —— 12MP 那档如果死在 load 或
    /// warmup 而不是计时循环里,靠最后一次心跳就能直接定位,不用猜。
    typealias Probe = (_ phase: String, _ valid: Int, _ attempts: Int,
                       _ lastMs: Double, _ peakMB: Double) -> Void

    static func run(frames: Int, computeUnits: MLComputeUnits, warmup: Int = 5,
                    modelNames: [String] = ["DiffMVS", "DiffMVS_PLACEHOLDER"],
                    probe: Probe? = nil) -> BenchResult {
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
        r.thermalBefore = thermalStateName(ProcessInfo.processInfo.thermalState)
        probe?("locate", 0, 0, 0, physFootprintMB())
        do {
            // compile if needed
            var compiled = url
            let tc = CFAbsoluteTimeGetCurrent()
            if url.pathExtension == "mlpackage" {
                probe?("compile", 0, 0, 0, physFootprintMB())
                compiled = try MLModel.compileModel(at: url)
            }
            r.compileSec = CFAbsoluteTimeGetCurrent() - tc
            let cfg = MLModelConfiguration()
            cfg.computeUnits = computeUnits
            let tl = CFAbsoluteTimeGetCurrent()
            probe?("load", 0, 0, 0, physFootprintMB())      // 12MP 最可能死在这一步
            let model = try MLModel(contentsOf: compiled, configuration: cfg)
            r.loadSec = CFAbsoluteTimeGetCurrent() - tl
            probe?("makeInputs", 0, 0, 0, physFootprintMB())
            let (provider, summary) = try makeRandomInputs(model.modelDescription)
            r.inputSummary = summary

            r.baselineMB = physFootprintMB()
            r.baselineAvailMB = availableMemMB()
            r.minAvailMB = r.baselineAvailMB
            r.budgetMB = r.baselineMB + r.baselineAvailMB
            for w in 0..<warmup {
                probe?("warmup", w, w, 0, physFootprintMB())   // 第一次真正吃满内存也在这里
                _ = try model.prediction(from: provider)
            }

            var times: [Double] = []
            var peak = physFootprintMB()
            let mon = CpuMonitor(); mon.start()          // sample CPU busy% during inference
            let sentinel = SuspensionSentinel()
            // 循环条件是"攒够 frames 个**干净**帧",不是"跑 frames 次"。被中断污染的
            // 帧作废后会自动补跑,所以拿到的永远是 frames 个纯前台测量。
            // maxAttempts 是防呆:真被反复打断时别无限跑下去,少几帧也要收敛。
            let maxAttempts = frames * 3 + 50
            var dropNext = false
            let t0 = CFAbsoluteTimeGetCurrent()
            while times.count < frames && r.attempts < maxAttempts {
                r.attempts += 1
                let e0 = sentinel.epoch
                let s = CFAbsoluteTimeGetCurrent()
                _ = try model.prediction(from: provider)
                let dt = (CFAbsoluteTimeGetCurrent() - s) * 1000.0
                if sentinel.epoch != e0 {
                    // 这一帧横跨了一次中断:整帧作废,并把紧随其后的一帧也丢掉
                    // (刚回前台那帧还带着 GPU 状态恢复的尾巴,同样不是稳态测量)。
                    r.discardedFrames += 1; dropNext = true; continue
                }
                if dropNext { r.discardedFrames += 1; dropNext = false; continue }
                times.append(dt)
                // footprint 与 available 必须**同时**取样:两者相加才是这一刻的真实上限,
                // 分开取样会被中间的分配/释放错开。
                let fp = physFootprintMB(), av = availableMemMB()
                peak = max(peak, fp)
                if av < r.minAvailMB { r.minAvailMB = av; r.budgetMB = fp + av }
                probe?("timing", times.count, r.attempts, dt, peak)
            }
            // 注意:totalSec 是墙钟总时长,**含**作废帧与挂起时间,只用来看整档花了多久;
            // 单帧统计(median/p90/first10/last10)一律只由干净帧算出。
            r.totalSec = CFAbsoluteTimeGetCurrent() - t0
            let (cpuMean, cpuPeak, cpuN, cores) = mon.stop()
            r.cpuMeanNorm = cpuMean; r.cpuPeakNorm = cpuPeak
            r.cpuSamples = cpuN; r.logicalCores = cores
            r.thermalAfter = thermalStateName(ProcessInfo.processInfo.thermalState)
            // drift windows BEFORE sorting (chronological order matters here)
            func med(_ v: [Double]) -> Double {
                guard !v.isEmpty else { return 0 }
                let s = v.sorted(); return s[s.count / 2]
            }
            r.first10MedianMs = med(Array(times.prefix(10)))
            r.last10MedianMs = med(Array(times.suffix(10)))
            times.sort()
            guard !times.isEmpty else {
                // 一帧干净的都没攒到(被反复打断)。宁可报失败,也不报一个污染过的数。
                r.message = "所有帧都被前后台切换污染,无有效测量(attempts=\(r.attempts))"
                return r
            }
            r.frames = times.count          // 实际进统计的干净帧数
            r.minMs = times.first ?? 0
            r.medianMs = times[times.count / 2]
            r.p90Ms = times[min(times.count - 1, Int(Double(times.count) * 0.9))]
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
