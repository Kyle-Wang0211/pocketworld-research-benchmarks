import SwiftUI
import UIKit
import CryptoKit

// 无头友好:启动即跑,结果落 Documents/SplatAB/splat_ab.json,
// 电脑侧 `devicectl device copy from` 取。
// 参数(devicectl process launch -- 之后透传):
//   -PWMode lod -PWOct oct_prod -PWLodArgs "mode=perf frames=900 rounds=3" -PWTag x
//                ⇒ LOD 台架,落 Documents/SplatAB/lod_<tag>.json
//   -PWK 100     每块帧数
//   -PWR 6       轮数(A/B 交替,逐轮翻转块内次序)
//   -PWWarm 30   每臂预热帧数
func docs() -> String {
    NSSearchPathForDirectoriesInDomains(.documentDirectory, .userDomainMask, true)[0]
}

func argInt(_ k: String, _ d: Int) -> Int {
    let a = ProcessInfo.processInfo.arguments
    if let i = a.firstIndex(of: k), i + 1 < a.count, let v = Int(a[i + 1]) { return v }
    return d
}

func argStr(_ k: String, _ d: String) -> String {
    let a = ProcessInfo.processInfo.arguments
    if let i = a.firstIndex(of: k), i + 1 < a.count { return a[i + 1] }
    return d
}

// 外壳探针:只有 OS 知道的量。thermalState 0..3 = nominal/fair/serious/critical,
// 与引擎约定的刻度一致;内存用 phys_footprint(Xcode 内存表同口径)。
let lodProbe: PwLodProbeFn = { out, _ in
    guard let out = out else { return }
    out.pointee.thermal_state = Int32(ProcessInfo.processInfo.thermalState.rawValue)
    var info = task_vm_info_data_t()
    var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<natural_t>.size)
    let kr = withUnsafeMutablePointer(to: &info) {
        $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
            task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
        }
    }
    out.pointee.footprint_mb = kr == KERN_SUCCESS ? Double(info.phys_footprint) / 1048576.0 : -1
    out.pointee.avail_mb = Double(os_proc_available_memory()) / 1048576.0
}

func lodVerify(_ dir: String, _ outPath: String) -> UnsafePointer<CChar>? {
    var rows: [String] = []
    for name in ["metadata.json", "hierarchy.bin", "octree.bin"] {
        let path = dir + "/" + name
        guard let h = FileHandle(forReadingAtPath: path) else {
            rows.append("\"\(name)\": {\"error\": \"missing\"}"); continue
        }
        var hasher = SHA256()
        var total: UInt64 = 0
        while true {
            let chunk = h.readData(ofLength: 16 << 20)
            if chunk.isEmpty { break }
            hasher.update(data: chunk)
            total += UInt64(chunk.count)
        }
        h.closeFile()
        let hex = hasher.finalize().map { String(format: "%02x", $0) }.joined()
        rows.append("\"\(name)\": {\"bytes\": \(total), \"sha256\": \"\(hex)\"}")
    }
    let json = "{\n  \"dir\": \"\(dir)\",\n  " + rows.joined(separator: ",\n  ") + "\n}\n"
    try? json.write(toFile: outPath, atomically: true, encoding: .utf8)
    return UnsafePointer(strdup(outPath))
}

final class Runner: ObservableObject {
    @Published var status = "准备中…"
    private var started = false
    func go() {
        if started { return }
        started = true
        let out = docs() + "/SplatAB"
        try? FileManager.default.createDirectory(atPath: out, withIntermediateDirectories: true)
        let K = argInt("-PWK", 100)
        let R = argInt("-PWR", 6)
        let W = argInt("-PWWarm", 30)
        // -PWMode points ⇒ 跑裸点云台架(bench_points.mm),落 points.json。
        // 默认 splat,保持既有跑法逐字不变(旧结果不受影响)。
        let mode = argStr("-PWMode", "splat")
        let cell = argInt("-PWCell", -1)
        let rad = argInt("-PWRad", 15)     // 0.1 px 为单位
        let tag = argStr("-PWTag", "")
        // run 1(09:53)在最后一格出现 1.8x 的断崖,三条臂同步掉 —— 多半是
        // 自动锁屏把合成器让了出来。第二遍把屏幕状态钉死,消掉这个混杂。
        UIApplication.shared.isIdleTimerDisabled = true
        NSLog("PWSPLATAB start mode=\(mode) K=\(K) R=\(R) warmup=\(W) cell=\(cell) rad=\(rad) tag=\(tag) out=\(out)")
        DispatchQueue.main.async { self.status = "跑中 \(mode) K=\(K) R=\(R)…" }
        DispatchQueue.global(qos: .userInitiated).async {
            let t0 = Date()
            let p: UnsafePointer<CChar>?
            if mode == "lodverify" {
                // 数据身份核对(外壳侧,CryptoKit):对 Documents/lod/<oct>/ 三个文件算 sha256,
                // 落 lod_verify_<oct>.json。🔴 整读 octree.bin 会把它灌进页缓存 ⇒
                // 必须在测帧率的那次启动【之后】单独跑,不能放在前面。
                let oct = argStr("-PWOct", "oct_prod")
                p = lodVerify(docs() + "/lod/" + oct, out + "/lod_verify_" + oct + "_" + tag + ".json")
            } else if mode == "lod" {
                // LOD 台架(Sources/lod/pw_lod_bench.cpp,平台无关 C++/Dawn)。
                // 八叉树由 `devicectl device copy to` 推进 Documents/lod/<name>/,
                // 外壳只负责两样 OS 才知道的东西:热状态、进程内存占用。
                let dir = docs() + "/lod/" + argStr("-PWOct", "oct_prod")
                let largs = argStr("-PWLodArgs", "mode=perf") + " tag=" + tag
                p = pwlod_run(dir, out, largs, lodProbe, nil)
            } else if mode == "cloud" {
                // cloud.bin 由 `devicectl device copy to` 推进 Documents,
                // **不开生产 app**(只读拷贝不算启动)。
                let cloudPath = docs() + "/" + argStr("-PWCloud", "cloud.bin")
                p = pwcloud_run(out, cloudPath, Int32(K), Int32(R), Int32(W),
                                Int32(argInt("-PWCam", 0)), Int32(rad),
                                Int32(argInt("-PWArms", 63)), tag)
            } else if mode == "points" {
                p = pwpoints_run(out, Int32(K), Int32(R), Int32(W),
                                 Int32(cell), Int32(rad), tag)
            } else {
                p = pwsplat_ab_run(out, Int32(K), Int32(R), Int32(W))
            }
            let s = p.map { String(cString: $0) } ?? "(null)"
            let dt = Date().timeIntervalSince(t0)
            NSLog("PWSPLATAB done in %.1fs -> %@", dt, s)
            DispatchQueue.main.async {
                self.status = String(format: "完成 %.1fs\n%@", dt, s)
            }
        }
    }
}

struct ContentView: View {
    @ObservedObject var r: Runner
    var body: some View {
        VStack(spacing: 12) {
            Text("PWSplatAB").font(.title2)
            Text(r.status).font(.system(size: 13, design: .monospaced))
                .multilineTextAlignment(.center).padding()
        }.onAppear { r.go() }
    }
}

@main
struct PWSplatABApp: App {
    @StateObject var r = Runner()
    var body: some Scene { WindowGroup { ContentView(r: r) } }
}
