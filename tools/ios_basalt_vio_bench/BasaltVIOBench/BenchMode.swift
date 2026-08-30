import Foundation

enum BenchMode: String, CaseIterable, Identifiable, Codable {
    case liveSoak = "live-soak"
    case replayPaced = "replay-paced"
    case replayMax = "replay-max"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .liveSoak: return "5 分钟真机持续测试"
        case .replayPaced: return "EuRoC 实时精度回放"
        case .replayMax: return "EuRoC 最大吞吐回放"
        }
    }
}

enum BenchPhase: String, Codable {
    case idle
    case preparing
    case warmup
    case measuring
    case draining
    case completed
    case failed
    case aborted
}

struct LiveSnapshot: Equatable {
    var elapsedSeconds = 0.0
    var firstUsablePoseLatencyMilliseconds: Double? = nil
    var processedFPS = 0.0
    var pipelineP95Milliseconds = 0.0
    var cameraDrops = 0
    var appDrops = 0
    var poseCount = 0
    var cpuCoreEquivalent = 0.0
    var footprintMB = 0.0
    var thermalState = "nominal"
    var batteryLevel: Double? = nil
}
