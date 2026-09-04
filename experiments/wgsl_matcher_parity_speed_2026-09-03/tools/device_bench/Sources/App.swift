import SwiftUI
import UIKit

// 无头友好:启动即跑,结果落 Documents/MatchBench/,电脑侧 devicectl copy from 取。
// 参数(devicectl process launch -- 之后透传):
//   -PWRows 13312   矩阵规模(夹具是 13312 行,取前 N 行 ⇒ 一份夹具跑任意规模)
//   -PWReps 9       交替轮数
//   -PWRatio 0.8
//   -PWFixture <名字>  Documents/fixtures/<名字>,默认 fx13
func docs() -> String { NSSearchPathForDirectoriesInDomains(.documentDirectory, .userDomainMask, true)[0] }

func argInt(_ k: String, _ d: Int) -> Int {
    let a = ProcessInfo.processInfo.arguments
    if let i = a.firstIndex(of: k), i + 1 < a.count, let v = Int(a[i + 1]) { return v }
    return d
}
func argDouble(_ k: String, _ d: Double) -> Double {
    let a = ProcessInfo.processInfo.arguments
    if let i = a.firstIndex(of: k), i + 1 < a.count, let v = Double(a[i + 1]) { return v }
    return d
}
func argStr(_ k: String, _ d: String) -> String {
    let a = ProcessInfo.processInfo.arguments
    if let i = a.firstIndex(of: k), i + 1 < a.count { return a[i + 1] }
    return d
}

final class Runner: ObservableObject {
    @Published var status = "准备中…"
    func go() {
        let out = docs() + "/MatchBench"
        try? FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)
        let fx = docs() + "/fixtures/" + argStr("-PWFixture", "fx13")
        let rows = argInt("-PWRows", 13312)
        let reps = argInt("-PWReps", 9)
        let ratio = argDouble("-PWRatio", 0.8)
        DispatchQueue.global(qos: .userInitiated).async {
            DispatchQueue.main.async { self.status = "跑 rows=\(rows) reps=\(reps)…" }
            let p = pwbench_run(fx, Int32(rows), Int32(reps), ratio, out)
            let s = p.map { String(cString: $0) } ?? ""
            DispatchQueue.main.async { self.status = s.isEmpty ? "失败(夹具缺失?)" : "完成 → \(s)" }
        }
    }
}

struct ContentView: View {
    @StateObject var r = Runner()
    var body: some View {
        VStack(spacing: 16) {
            Text("PWMatchBench").font(.title2)
            Text(r.status).font(.footnote).multilineTextAlignment(.center).padding()
        }
        .onAppear { r.go() }
    }
}

@main
struct PWMatchBenchApp: App {
    var body: some Scene { WindowGroup { ContentView() } }
}
