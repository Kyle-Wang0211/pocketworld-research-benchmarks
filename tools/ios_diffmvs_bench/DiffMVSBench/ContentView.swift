import SwiftUI
import CoreML
import UIKit

struct ContentView: View {
    @State private var frames = 414
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
        .onAppear { if !running { runOverlapProbe() } }   // auto-run DiffMVS CoreML CPU-idle sweep; writes JSON to container (unplug-safe)
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
