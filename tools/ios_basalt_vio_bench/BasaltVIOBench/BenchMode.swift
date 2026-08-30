import Foundation

enum BenchMode: String, CaseIterable, Identifiable, Codable {
    /// One hand-held capture. The ARKit arm runs live while ARFrame.capturedImage
    /// and CoreMotion are persisted, giving every candidate byte-identical input
    /// from one physical trajectory. iOS grants the rear camera to a single
    /// session, so recording from ARKit's own frames is what makes one capture
    /// serve all three arms.
    case record = "record"
    case liveSoak = "live-soak"
    /// Replays the device recording. This is where candidates are scored.
    case replayDeviceRecording = "replay-device-recording"
    case replayPaced = "replay-paced"
    case replayMax = "replay-max"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .record: return "录制一次(ARKit 直播 + 存帧)"
        case .liveSoak: return "真机短诊断"
        case .replayDeviceRecording: return "回放本机录制(计分)"
        case .replayPaced: return "EuRoC 实时精度回放"
        case .replayMax: return "EuRoC 最大吞吐回放"
        }
    }
}

extension BenchMode {
    /// Replay modes consume a persisted manifest instead of opening a camera.
    var isReplay: Bool {
        switch self {
        case .replayDeviceRecording, .replayPaced, .replayMax: return true
        case .record, .liveSoak: return false
        }
    }

    /// EuRoC is the only channel with external ground truth, so it is the only
    /// one that may produce an absolute accuracy number.
    var hasExternalGroundTruth: Bool {
        switch self {
        case .replayPaced, .replayMax: return true
        case .record, .liveSoak, .replayDeviceRecording: return false
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
