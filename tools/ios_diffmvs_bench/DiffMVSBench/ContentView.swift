import SwiftUI
import CoreML

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
        .onAppear { if result == nil && !running { runBench() } }   // auto-run single CPU+GPU bench for terminal capture
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
