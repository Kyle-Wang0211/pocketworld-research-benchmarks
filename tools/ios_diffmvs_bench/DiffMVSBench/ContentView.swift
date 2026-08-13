import SwiftUI
import CoreML
import UIKit

struct ContentView: View {
    @State private var frames = 100   // [2026-07-31 用户签决] 100 帧够出中位数,别再跑 414
    @State private var unitChoice = 0          // 0=CPU+GPU(best) 1=ALL 2=CPU
    @State private var running = false
    @State private var result: BenchResult?

    // CPU+GPU first: on Mac CoreML it was 127ms vs ALL 1869ms — ANE thrashes on
    // 3D-conv/grid_sample, so .all is a trap here. Confirm the ordering on device.
    let unitOptions: [(String, MLComputeUnits)] = [
        ("CPU+GPU (推荐)", .cpuAndGPU),
        ("ALL (ANE+GPU+CPU)", .all),
        ("CPU only", .cpuOnly),
    ]

    var body: some View {
        NavigationView {
            Form {
                Section("配置") {
                    Stepper("帧数: \(frames)", value: $frames, in: 1...2000, step: 50)
                    Picker("Compute Units", selection: $unitChoice) {
                        ForEach(0..<unitOptions.count, id: \.self) { Text(unitOptions[$0].0) }
                    }
                }
                Section {
                    Button(running ? "跑测中…" : "运行 Benchmark") {
                        runBench()
                    }.disabled(running)
                }
                Section("ARKit") {
                    NavigationLink("覆盖预览 (red/yellow/green)") {
                        CoveragePreviewView()
                    }
                }
                if let r = result {
                    Section("结果") {
                        row("模型", r.message)
                        row("Compute", r.computeUnits)
                        row("输入", r.inputSummary)
                        if r.ok {
                            row("单帧 中位", String(format: "%.1f ms", r.medianMs))
                            row("单帧 p90", String(format: "%.1f ms", r.p90Ms))
                            row("单帧 最快", String(format: "%.1f ms", r.minMs))
                            row("\(r.frames) 帧总计", String(format: "%.1f s", r.totalSec))
                            row("基线内存", String(format: "%.0f MB", r.baselineMB))
                            row("峰值内存(phys_footprint)", String(format: "%.0f MB", r.peakMB))
                            row("vs 4.1GB 上限", String(format: "%.0f%%", r.peakMB / 4198.0 * 100))
                        }
                    }
                }
            }
            .navigationTitle("DiffMVS Bench")
        }
        .onAppear { if !running { runResolutionSweepBig() } }   // [2026-07-31] 第二轮:只打 5.4Mpx/12MP 两档大的
    }

    /// 第二轮:只跑 2688x2016(5.42Mpx)与 4032x3008(12.13Mpx 原图)两档。
    ///
    /// 为什么单独一轮而不是把梯子接长:小档那 7 个已经跑完并落盘了,重跑一遍要多花
    /// 半小时,而且大档极可能被 jetsam 杀 —— 杀了会把同一个 JSON 里已有的小档结果
    /// 一起断在半路。所以换个文件名单独写,小档那份结果动都不动。
    ///
    /// 开跑前先空转 120s:整轮小档跑下来手机一直是 serious,不降温的话大档拿到的是
    /// 别人烧出来的热债。
    func runResolutionSweepBig() {
        running = true; result = nil
        UIApplication.shared.isIdleTimerDisabled = true
        // [2026-07-31 19:10 改] 2688x2016(5.42Mpx) 已由内核判决,不再跑:
        // JetsamEvent-2026-07-31-184911.ips 逐字记录 rpages=277804(4341MB) reason=highwater,
        // 死在第一次 warmup 预测里。再跑一次只会再触发一场 jetsam 风暴 —— 上一场把
        // containermanagerd/bird 一起杀了,设备的 developer 服务直接瘫痪,得重启才恢复。
        //
        // 所以梯子改成:先用 2304(3.98) / 2560(4.92) 把墙夹紧(这两档预计能活),
        // 必死的 12MP 放到最后 —— 让那场必然的风暴发生在所有有用数据都已落盘之后。
        // [2026-07-31 20:40 用户纠正] 目标是兼容 iPhone 11(预算 2098MB),所以 >2GB 的档
        // 测了对适配决策没用。已知:1600x1152=1683MB(过)、2048x1536=2363MB(超),
        // 2688x2016 已被内核判死(4341MB highwater)。真正要夹的是 2098MB 那条线,
        // 按实测斜率 870MB/Mpx 落在约 2.31Mpx —— 所以只跑这一段的三档。
        // 12MP 不再跑:2688(5.42Mpx)已经撞穿 4341MB,12.13Mpx 是它的 2.2 倍,结论已定。
        let ladder: [(String, Double)] = [
            ("CasDiffMVS_1664x1248", 2.077), ("CasDiffMVS_1728x1280", 2.212),
            ("CasDiffMVS_1792x1344", 2.408),
        ]
        let f = 100
        let cooldownSec: UInt32 = 120
        DispatchQueue.global(qos: .userInitiated).async {
            let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
            let jsonURL = docs?.appendingPathComponent("casdiffmvs_resolution_sweep_big.json")
            // 断点续跑:上一轮实测里 app 被(误)重新打开过一次,onAppear 重跑把已经
            // 落盘的 5 档结果整个覆盖了。12MP 这档单跑就要半小时,再被清零一次代价
            // 太大 —— 所以开跑前先读回已有 JSON,ok=true 的档直接跳过。
            var done: [String: [String: Any]] = [:]
            // 死亡计数:一条停在 STARTED 的记录 = 上一轮在这档里进程没了(jetsam)。
            // 不记这个的话,必死的那档会把后面的档永远挡住 —— 重开→再死→再重开,
            // 12MP 那档永远轮不到。容忍一次(可能只是误触重开 app),第二次判死跳过。
            var deaths: [String: Int] = [:]
            if let u = jsonURL, let data = try? Data(contentsOf: u),
               let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let prev = obj["results"] as? [[String: Any]] {
                for e in prev {
                    guard let res = e["resolution"] as? String else { continue }
                    if (e["ok"] as? Bool) == true { done[res] = e; continue }
                    if (e["status"] as? String) == "STARTED" || (e["verdict"] as? String) != nil {
                        deaths[res] = ((e["deaths"] as? Int) ?? 0) + 1
                    }
                }
            }
            var arr: [[String: Any]] = []
            func flush() {
                let payload: [String: Any] = ["device": UIDevice.current.name,
                    "systemVersion": UIDevice.current.systemVersion,
                    "note": "casdiffmvs fp32 CPU+GPU big resolutions (5.4Mpx / 12MP)",
                    "framesPerRes": f, "cooldownSec": Int(cooldownSec),
                    "results": arr]
                if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]),
                   let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first {
                    try? data.write(to: dir.appendingPathComponent("casdiffmvs_resolution_sweep_big.json"))
                }
            }
            var last: BenchResult?
            for (name, mpx) in ladder {
                let res = name.replacingOccurrences(of: "CasDiffMVS_", with: "")
                if let cached = done[res] { arr.append(cached); flush(); done.removeValue(forKey: res); continue }   // 已跑过,原样带回
                if let d = deaths[res], d >= 2 {
                    // 连死两次:这档就是跑不动。判决落盘后跳过,把机会让给后面的档。
                    arr.append(["resolution": res, "mpx": mpx, "model": name, "ok": false,
                                "verdict": "JETSAM-KILLED", "deaths": d,
                                "message": "连续 \(d) 次在本档进程消失(jetsam highwater),判定超预算"])
                    flush(); continue
                }
                let priorDeaths = deaths[res] ?? 0   // 带进下面那条 STARTED,下一轮才能继续累加
                sleep(cooldownSec)   // 每档前都降温(首档也是:上一轮整轮都停在 serious)
                // 12MP 这档很可能在 load/warmup 阶段就被 jetsam 直接 SIGKILL,
                // 那时进程没有任何收尾机会 —— STARTED 这条就是唯一的死亡证明。
                arr.append(["resolution": res, "mpx": mpx, "model": name, "status": "STARTED",
                            "deaths": priorDeaths,
                            "thermalAtStart": thermalStateName(ProcessInfo.processInfo.thermalState)])
                flush()
                // 心跳探针:每帧(以及 compile/load/warmup 每个阶段)覆写一个小 JSON。
                // 拉这个文件就知道"现在跑到哪一档的第几帧、峰值多少"。app 若被 jetsam
                // 杀掉,文件停在最后一次心跳 —— 死亡瞬间的阶段和内存就留在那儿了。
                let probe: Benchmark.Probe = { phase, valid, attempts, lastMs, peakMB in
                    let p: [String: Any] = [
                        "resolution": res, "mpx": mpx, "phase": phase,
                        "validFrames": valid, "targetFrames": f, "attempts": attempts,
                        "lastMs": lastMs, "peakMB": peakMB,
                        "pctOf4_1GB": peakMB / 4198.0 * 100,
                        "thermal": thermalStateName(ProcessInfo.processInfo.thermalState),
                        "wallClock": ISO8601DateFormatter().string(from: Date()),
                    ]
                    if let data = try? JSONSerialization.data(withJSONObject: p, options: [.prettyPrinted]),
                       let dir = docs {
                        try? data.write(to: dir.appendingPathComponent("bench_progress.json"))
                    }
                }
                let r = Benchmark.run(frames: f, computeUnits: .cpuAndGPU, modelNames: [name],
                                      probe: probe)
                NSLog("PWBIG %@ ok=%d median=%.1fms peakMB=%.0f thermal=%@->%@",
                      res, r.ok ? 1 : 0, r.medianMs, r.peakMB, r.thermalBefore, r.thermalAfter)
                arr[arr.count - 1] = ["resolution": res, "mpx": mpx, "model": name,
                            "ok": r.ok, "message": r.message,
                            "frames": r.frames, "medianMs": r.medianMs, "p90Ms": r.p90Ms,
                            "minMs": r.minMs, "totalSec": r.totalSec,
                            "first10MedianMs": r.first10MedianMs, "last10MedianMs": r.last10MedianMs,
                            "baselineMB": r.baselineMB, "peakMB": r.peakMB,
                            "compileSec": r.compileSec, "loadSec": r.loadSec,
                            "thermalBefore": r.thermalBefore, "thermalAfter": r.thermalAfter,
                            "cpuMeanNorm": r.cpuMeanNorm, "cpuPeakNorm": r.cpuPeakNorm,
                            "discardedFrames": r.discardedFrames, "attempts": r.attempts,
                            "computeUnits": r.computeUnits, "input": r.inputSummary]
                flush()
                if r.ok { last = r }
            }
            // 梯子之外的历史结果也要留住:上一轮换梯子时,1600/2048 的记录被整个覆盖了
            // (它们不在新梯子里,就没被 append 回去)。历史数据不该因为换梯子而消失。
            for (_, e) in done { arr.append(e) }
            flush()
            NSLog("PWBIG DONE")
            DispatchQueue.main.async {
                result = last; running = false
                UIApplication.shared.isIdleTimerDisabled = false
            }
        }
    }

    /// [2026-07-31 用户要求"别推测,做个真机 bench 测一下",并签决"100 帧"] CasDiffMVS
    /// 分辨率梯子:每档一个独立导出的 mlpackage(输入形状是 trace 死的,换分辨率必须重导)。
    ///
    /// 目的:回答"12MP 原图能不能直喂"。此前只有按像素数线性外推的估算,没有测量。
    /// 梯子只到 2048x1536(3.15Mpx):2688x2016 这一档在 Mac 上导出时把 18GB 撑爆了,
    /// 更大的两档没有 mlpackage。手机这边先测已有的 7 档,曲线+内存墙足以判死或放行。
    ///
    /// 关键设计:
    /// 1. **逐档增量写盘**。大分辨率一定可能撞 jetsam 被 SIGKILL,那时进程直接没了、
    ///    没有任何收尾机会 —— 只有已经落盘的档能留下来。被杀在哪一档本身就是最重要的
    ///    那个数据点,所以每档开跑前先写一条 STARTED。
    /// 2. **升序跑**(按 Mpx 不是按名字:768x576=0.442 < 896x512=0.459),同上,让被杀
    ///    发生在尽可能靠后的位置。
    /// 3. **档间 60s 空转降温 + 记录 thermalState 与 first10/last10 中位**。7 档 ×100 帧
    ///    会把 SoC 热透,否则大分辨率的慢分不清是像素多还是降频 —— 让热偏差可见,而不是
    ///    悄悄烙进分辨率曲线里。
    func runResolutionSweep() {
        running = true; result = nil
        UIApplication.shared.isIdleTimerDisabled = true
        // 与 export_bench_resolutions.py 的梯子一一对应(只列已成功导出的档)。
        let ladder: [(String, Double)] = [
            ("CasDiffMVS_768x576", 0.442), ("CasDiffMVS_896x512", 0.459),
            ("CasDiffMVS_896x672", 0.602), ("CasDiffMVS_1024x768", 0.786),
            ("CasDiffMVS_1280x960", 1.229), ("CasDiffMVS_1600x1152", 1.843),
            ("CasDiffMVS_2048x1536", 3.146),
        ]
        let f = 100
        let cooldownSec: UInt32 = 60
        DispatchQueue.global(qos: .userInitiated).async {
            var arr: [[String: Any]] = []
            func flush() {
                let payload: [String: Any] = ["device": UIDevice.current.name,
                    "systemVersion": UIDevice.current.systemVersion,
                    "note": "casdiffmvs fp32 CPU+GPU resolution ladder",
                    "framesPerRes": f, "cooldownSec": Int(cooldownSec),
                    "results": arr]
                if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]),
                   let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first {
                    try? data.write(to: dir.appendingPathComponent("casdiffmvs_resolution_sweep.json"))
                }
            }
            var last: BenchResult?
            for (i, (name, mpx)) in ladder.enumerated() {
                if i > 0 { sleep(cooldownSec) }   // 降温,别让大档背别人的热债
                let res = name.replacingOccurrences(of: "CasDiffMVS_", with: "")
                arr.append(["resolution": res, "mpx": mpx, "model": name, "status": "STARTED",
                            "thermalAtStart": thermalStateName(ProcessInfo.processInfo.thermalState)])
                flush()   // 被 SIGKILL 也留得下
                let r = Benchmark.run(frames: f, computeUnits: .cpuAndGPU, modelNames: [name])
                NSLog("PWRES %@ ok=%d median=%.1fms peakMB=%.0f thermal=%@->%@",
                      res, r.ok ? 1 : 0, r.medianMs, r.peakMB, r.thermalBefore, r.thermalAfter)
                arr[arr.count - 1] = ["resolution": res, "mpx": mpx, "model": name,
                            "ok": r.ok, "message": r.message,
                            "frames": r.frames, "medianMs": r.medianMs, "p90Ms": r.p90Ms,
                            "minMs": r.minMs, "totalSec": r.totalSec,
                            "first10MedianMs": r.first10MedianMs, "last10MedianMs": r.last10MedianMs,
                            "baselineMB": r.baselineMB, "peakMB": r.peakMB,
                            "compileSec": r.compileSec, "loadSec": r.loadSec,
                            "thermalBefore": r.thermalBefore, "thermalAfter": r.thermalAfter,
                            "cpuMeanNorm": r.cpuMeanNorm, "cpuPeakNorm": r.cpuPeakNorm,
                            "computeUnits": r.computeUnits, "input": r.inputSummary]
                flush()
                if r.ok { last = r }
            }
            NSLog("PWRES DONE")
            DispatchQueue.main.async {
                result = last; running = false
                UIApplication.shared.isIdleTimerDisabled = false
            }
        }
    }

    /// fp16-vs-fp32 speed+memory on A16, casdiffmvs, CPU+GPU ONLY (never ANE:
    /// Apple-only + garbages 3D-conv). Writes Documents/casdiffmvs_precision.json.
    func runPrecisionCompare() {
        running = true; result = nil
        UIApplication.shared.isIdleTimerDisabled = true
        let models: [(String, String)] = [("fp16", "CasDiffMVS_fp16"), ("fp32", "CasDiffMVS_fp32")]
        let f = 20
        DispatchQueue.global(qos: .userInitiated).async {
            var arr: [[String: Any]] = []
            var last: BenchResult?
            func flush() {   // write INCREMENTALLY so an OOM/SIGKILL on a later model keeps earlier results
                let payload: [String: Any] = ["device": UIDevice.current.name,
                    "systemVersion": UIDevice.current.systemVersion, "results": arr]
                if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]),
                   let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first {
                    try? data.write(to: dir.appendingPathComponent("casdiffmvs_precision.json"))
                }
            }
            for (tag, name) in models {
                arr.append(["precision": tag, "status": "STARTED"]); flush()   // mark start (survives crash)
                let r = Benchmark.run(frames: f, computeUnits: .cpuAndGPU, modelNames: [name])
                print(String(format: "PWPREC| %@ ok=%d median=%.1fms peakMB=%.0f", tag, r.ok ? 1 : 0, r.medianMs, r.peakMB))
                NSLog("PWPREC %@ median=%.1fms peakMB=%.0f", tag, r.medianMs, r.peakMB)
                arr[arr.count - 1] = ["precision": tag, "model": name, "ok": r.ok, "message": r.message,
                            "frames": r.frames, "medianMs": r.medianMs, "p90Ms": r.p90Ms, "minMs": r.minMs,
                            "totalSec": r.totalSec, "baselineMB": r.baselineMB, "peakMB": r.peakMB,
                            "computeUnits": r.computeUnits, "input": r.inputSummary]
                flush()
                last = r
            }
            print("PWPREC| DONE")
            DispatchQueue.main.async {
                result = last; running = false
                UIApplication.shared.isIdleTimerDisabled = false
            }
        }
    }

    /// On-device GPU-CPU-overlap headroom probe. Runs the REAL DiffMVS CoreML model
    /// in a tight loop across 3 compute-unit configs, sampling device-normalized
    /// process CPU% during each. 100 − cpuMeanNorm ≈ CPU left for a concurrent
    /// fusion stage. Writes Documents/diffmvs_overlap_probe.json for devicectl copy
    /// (no --console: unplug-safe per device-test standard). isIdleTimerDisabled so
    /// the screen won't sleep mid-run.
    func runOverlapProbe() {
        running = true; result = nil
        UIApplication.shared.isIdleTimerDisabled = true
        let sweep: [(String, MLComputeUnits)] = [
            ("CPU+GPU", .cpuAndGPU), ("ALL", .all), ("CPU", .cpuOnly),
        ]
        let f = 60
        DispatchQueue.global(qos: .userInitiated).async {
            var arr: [[String: Any]] = []
            var last: BenchResult?
            for (name, u) in sweep {
                let r = Benchmark.run(frames: f, computeUnits: u)
                print(String(format: "PWOV| %@ ok=%d median=%.1fms p90=%.1fms peakMB=%.0f cpuMeanNorm=%.1f%% cpuPeakNorm=%.1f%% samples=%d cores=%d",
                             name, r.ok ? 1 : 0, r.medianMs, r.p90Ms, r.peakMB,
                             r.cpuMeanNorm, r.cpuPeakNorm, r.cpuSamples, r.logicalCores))
                NSLog("PWOV %@ median=%.1fms cpuMeanNorm=%.1f%%", name, r.medianMs, r.cpuMeanNorm)
                arr.append([
                    "config": name, "ok": r.ok, "message": r.message, "input": r.inputSummary,
                    "frames": r.frames, "medianMs": r.medianMs, "p90Ms": r.p90Ms, "minMs": r.minMs,
                    "totalSec": r.totalSec, "baselineMB": r.baselineMB, "peakMB": r.peakMB,
                    "cpuMeanNorm": r.cpuMeanNorm, "cpuPeakNorm": r.cpuPeakNorm,
                    "cpuSamples": r.cpuSamples, "logicalCores": r.logicalCores,
                ])
                last = r
            }
            let payload: [String: Any] = [
                "device": UIDevice.current.name,
                "systemVersion": UIDevice.current.systemVersion,
                "processorCount": ProcessInfo.processInfo.processorCount,
                "results": arr,
            ]
            if let data = try? JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted]),
               let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first {
                let url = dir.appendingPathComponent("diffmvs_overlap_probe.json")
                try? data.write(to: url)
                print("PWOV| WROTE \(url.path)")
            }
            print("PWOV| DONE")
            DispatchQueue.main.async {
                result = last; running = false
                UIApplication.shared.isIdleTimerDisabled = false
            }
        }
    }

    // Stage-1 (SfM) real on-device benchmark: C++ kernels (matching + extraction)
    // run on the device CPU, extrapolated to v6's full 414-frame / 6159-pair workload.
    func runSfmBench() {
        DispatchQueue.global(qos: .userInitiated).async {
            let cores = Int(pw_num_cores())
            let nd = 8192, pm = 3
            let perPair1  = pw_bench_match(Int32(nd), Int32(pm), 1)        / Double(pm)   // single-thread
            let perPairN  = pw_bench_match(Int32(nd), Int32(pm), 0)        / Double(pm)   // all cores
            let perImg    = pw_bench_extract(2048, 1152, 5, 0)                            // one image, single-thread
            let v6Pairs = 6159, v6Frames = 414
            let matchSec   = perPairN * Double(v6Pairs) / 1000.0                          // matching is all-cores per pair
            let extractSec = perImg * Double(v6Frames) / Double(cores) / 1000.0           // COLMAP threads across images
            let stage1Sec  = matchSec + extractSec                                        // (+ GLOMAP BA, measured separately)
            print(String(format: "PWSFM| cores=%d", cores))
            print(String(format: "PWSFM| match perPair: 1thread=%.0fms allcores=%.0fms speedup=%.1fx (brute-force; FLANN would be faster)",
                         perPair1, perPairN, perPair1/perPairN))
            // GPU brute-force match (Metal, one thread per query) on the same nd/pm workload
            let gpuTotal  = pwBenchMatchGPU(numDesc: nd, numPairs: pm)
            if gpuTotal >= 0 {
                let perPairGPU = gpuTotal / Double(pm)
                print(String(format: "PWSFM| match GPU perPair=%.0fms (total=%.0fms over %d pairs @%dfeat) vs CPU allcores=%.0fms speedup=%.1fx",
                             perPairGPU, gpuTotal, pm, nd, perPairN, perPairN/perPairGPU))
            } else {
                print("PWSFM| match GPU unavailable (Metal init failed)")
            }
            print(String(format: "PWSFM| extract perImage(2048x1152,5oct)=%.0fms", perImg))
            print(String(format: "PWSFM| v6 EXTRACT est = %.0f s (%.1f min) [%d frames / %d cores]",
                         extractSec, extractSec/60, v6Frames, cores))
            print(String(format: "PWSFM| v6 MATCH   est = %.0f s (%.1f min) [%d pairs, brute-force]",
                         matchSec, matchSec/60, v6Pairs))
            print(String(format: "PWSFM| STAGE-1 (extract+match, no BA) = %.0f s (%.1f min)", stage1Sec, stage1Sec/60))
            // realistic product config: ~80 keyframes, K=25 NN -> ~1000 pairs, 2048 features
            let perPair2k = pw_bench_match(2048, 3, 0) / 3.0
            let realPairs = 1000.0, realFrames = 80.0
            let realMatch = perPair2k * realPairs / 1000.0
            let realExtract = perImg * realFrames / Double(cores) / 1000.0
            print(String(format: "PWSFM| [realistic] perPair@2048feat allcores=%.0fms", perPair2k))
            print(String(format: "PWSFM| [realistic] 80keyframes/~1000pairs/2048feat: extract=%.0fs match=%.0fs stage1(noBA)=%.0fs (%.1f min) CPU-bruteforce",
                         realExtract, realMatch, realExtract+realMatch, (realExtract+realMatch)/60))
            // ---- INCREMENTAL per-frame: user captures ~1 photo / 1-3s, run SfM as frames arrive ----
            // each new frame: extract (CPU) + match vs K spatial-neighbor keyframes on GPU (ARKit-pose prior)
            let K = 20
            for nd in [2048, 4096, 8192] {
                let mGPU = pwBenchMatchGPU(numDesc: nd, numPairs: K)   // new frame vs K neighbors, GPU
                let exCPU = perImg                                     // extract 1 frame on CPU (~const)
                let serial = exCPU + mGPU
                let pipelined = max(exCPU, mGPU)                       // CPU extract(N+1) overlaps GPU match(N)
                print(String(format: "PWSFM| [incremental] %dfeat newframe-vs-%dnbr: extractCPU=%.0fms matchGPU=%.0fms serial=%.0fms pipelined=%.0fms -> %@",
                             nd, K, exCPU, mGPU, serial, pipelined, pipelined <= 3000 ? "FITS 1-3s/photo" : "EXCEEDS"))
            }
            NSLog("PWSFM stage1=%.0fs realMatch=%.0fs", stage1Sec, realMatch)
        }
    }

    // run CPU+GPU then ALL (then CPU) and print each, so one launch compares them
    func runSweep() {
        running = true; result = nil
        let sweep: [(String, MLComputeUnits)] = [
            ("CPU+GPU", .cpuAndGPU), ("ALL", .all), ("CPU", .cpuOnly),
        ]
        let f = 80
        DispatchQueue.global(qos: .userInitiated).async {
            var last: BenchResult?
            for (name, u) in sweep {
                let r = Benchmark.run(frames: f, computeUnits: u)
                print(String(format: "PWSWEEP| %@ median=%.1fms p90=%.1fms min=%.1fms peakMB=%.0f",
                             name, r.medianMs, r.p90Ms, r.minMs, r.peakMB))
                NSLog("PWSWEEP %@ median=%.1fms", name, r.medianMs)
                last = r
            }
            DispatchQueue.main.async { result = last; running = false }
        }
    }

    func row(_ k: String, _ v: String) -> some View {
        HStack { Text(k).foregroundColor(.secondary); Spacer(); Text(v).multilineTextAlignment(.trailing) }
    }

    func runBench() {
        running = true; result = nil
        let f = frames; let u = unitOptions[unitChoice].1
        DispatchQueue.global(qos: .userInitiated).async {
            let r = Benchmark.run(frames: f, computeUnits: u)
            // stdout markers so a terminal (devicectl --console) can capture results
            print("PWBENCH| \(r.message)")
            print("PWBENCH| compute=\(r.computeUnits) input=\(r.inputSummary)")
            print(String(format: "PWBENCH| frames=%d median=%.1fms p90=%.1fms min=%.1fms total=%.1fs",
                         r.frames, r.medianMs, r.p90Ms, r.minMs, r.totalSec))
            print(String(format: "PWBENCH| baselineMB=%.0f peakMB=%.0f vs4.1GB=%.0f%%",
                         r.baselineMB, r.peakMB, r.peakMB / 4198.0 * 100))
            NSLog("PWBENCH median=%.1fms peakMB=%.0f", r.medianMs, r.peakMB)
            DispatchQueue.main.async { result = r; running = false }
        }
    }
}
