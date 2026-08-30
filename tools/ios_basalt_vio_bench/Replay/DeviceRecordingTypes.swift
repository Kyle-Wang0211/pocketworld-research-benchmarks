import Foundation

/// On-disk shape of one device recording.
///
/// The recording is the shared input that lets one hand-held capture serve every
/// arm. It stores the luma plane of `ARFrame.capturedImage` exactly as the engine
/// will receive it, so replaying it is feeding the same input, not a substitute
/// for it.
///
/// Frames are raw, one file each, never encoded. PNG or HEVC would put an encoder
/// on the capture path and, in the lossy case, would change the pixels the
/// algorithm sees. At 1920x1440 a frame is 2,764,800 bytes and 300 s is ~23.2
/// GiB; that cost is accepted rather than compressed away.
enum DeviceRecordingFileRole: String, Codable, CaseIterable, Sendable {
    case cameraIndex = "camera_index"
    /// Per-frame intrinsics, one JSON row per frame, mirroring the per-photo
    /// sidecar production already writes: the same `t` and `intrinsics_fxfycxcy`
    /// keys, pinned to the frame they came from. Production takes that care
    /// because autofocus moves the focal length during a scan and it carries a
    /// per-sample focusStable flag alongside. Keeping only frame 0's values, as
    /// this recorder did, pins a whole capture to whatever focus position the
    /// first frame happened to have.
    case intrinsicsIndex = "intrinsics_index"
    case imuIndex = "imu_index"
    case arkitPoses = "arkit_poses"
}

struct DeviceRecordingFile: Codable, Equatable, Sendable {
    let role: DeviceRecordingFileRole
    let relativePath: String
    var byteCount: Int64
    var sha256: String

    enum CodingKeys: String, CodingKey {
        case role
        case relativePath = "relative_path"
        case byteCount = "byte_count"
        case sha256
    }
}

struct DeviceRecordingCameraFormat: Codable, Equatable, Sendable {
    var width: Int
    var height: Int
    var pixelFormat: String
    var nominalFPS: Double

    enum CodingKeys: String, CodingKey {
        case width, height
        case pixelFormat = "pixel_format"
        case nominalFPS = "nominal_fps"
    }

    static let scoring = DeviceRecordingCameraFormat(
        width: BenchResolution.scoring.width,
        height: BenchResolution.scoring.height,
        pixelFormat: "luma8_from_420f_full_range",
        nominalFPS: 30
    )

    var bytesPerFrame: Int { width * height }
}

struct DeviceRecordingIntrinsics: Codable, Equatable, Sendable {
    var fx: Double
    var fy: Double
    var cx: Double
    var cy: Double
    /// Always `ARFrame.camera.intrinsics`; recorded so a reader never has to
    /// guess whether a value was measured or extrapolated.
    var source: String
    /// Result of `ARKitIntrinsicsCrossCheck` at record time.
    var crossCheckPassed: Bool

    enum CodingKeys: String, CodingKey {
        case fx, fy, cx, cy, source
        case crossCheckPassed = "cross_check_passed"
    }

    var asCameraIntrinsics: CameraIntrinsics {
        CameraIntrinsics(fx: fx, fy: fy, cx: cx, cy: cy)
    }
}

struct DeviceRecordingManifest: Codable, Equatable, Sendable {
    let schemaVersion: Int
    let recordingID: String
    var camera: DeviceRecordingCameraFormat
    var intrinsics: DeviceRecordingIntrinsics
    var frameCount: Int
    var imuSampleCount: Int
    /// One streaming SHA-256 over every frame's bytes in capture order.
    ///
    /// Hashing 9,000 files individually would cost 9,000 digests to verify a
    /// single logical object. One rolling digest gives the same integrity
    /// guarantee in one pass, and it is computed incrementally while recording
    /// so it costs nothing extra.
    var framesDigestSHA256: String
    var framesTotalByteCount: Int64
    /// Any dropped frame, dropped IMU sample or short write. A recording with
    /// losses is not a shorter recording; it is an invalid one.
    var lossCount: Int
    /// Loss split by cause. A single total said a recording was lossy without
    /// saying whether the pixel format was wrong, the write queue fell behind,
    /// or the filesystem returned an error -- three unrelated faults with three
    /// unrelated fixes, and no way to tell them apart after the fact.
    var lossFormatMismatch: Int = 0
    var lossWriteQueueFull: Int = 0
    var lossWriteError: Int = 0
    /// High-water mark of frames awaiting write, against a queue depth of 8.
    /// A run that never approached the cap did not lose frames to disk speed.
    var peakInFlight: Int = 0
    /// Slowest single frame write. Names the stall when the queue does fill.
    var slowestWriteMilliseconds: Double = 0
    /// Spread of the focal length across the recording. A wide range means
    /// autofocus moved while capturing and no single value describes the run.
    var focalLengthMinimum: Double = 0
    var focalLengthMaximum: Double = 0
    var files: [DeviceRecordingFile]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case recordingID = "recording_id"
        case camera, intrinsics, files
        case frameCount = "frame_count"
        case imuSampleCount = "imu_sample_count"
        case framesDigestSHA256 = "frames_digest_sha256"
        case framesTotalByteCount = "frames_total_byte_count"
        case lossCount = "loss_count"
        case lossFormatMismatch = "loss_format_mismatch"
        case lossWriteQueueFull = "loss_write_queue_full"
        case lossWriteError = "loss_write_error"
        case peakInFlight = "peak_in_flight"
        case slowestWriteMilliseconds = "slowest_write_ms"
        case focalLengthMinimum = "focal_length_min"
        case focalLengthMaximum = "focal_length_max"
    }

    static let supportedSchemaVersion = 1
    static let framesDirectory = "frames"

    static func frameRelativePath(index: Int) -> String {
        "\(framesDirectory)/\(String(format: "%08d", index)).y"
    }
}

/// A recording replayed as the same event stream `ReplayScheduler` already
/// drives for EuRoC, so the pacing, ordering and delivery path are shared rather
/// than duplicated.
struct DeviceRecordingDataset: Sendable {
    let recordingID: String
    let camera: DeviceRecordingCameraFormat
    let intrinsics: DeviceRecordingIntrinsics
    let events: [ReplayEvent]
    /// ARKit's trajectory over the identical frames. A same-input system
    /// reference for comparison; never ground truth, and never an accuracy
    /// denominator.
    let arkitReference: [TimedPose]

    var inputCameraCount: Int { 1 }
}

/// `LocalizedError`, not just `CustomStringConvertible`.
///
/// Swift bridges a bare `Error` to NSError, and `localizedDescription` then
/// yields "The operation couldn't be completed. (DeviceRecordingError error 12.)"
/// -- which is what the operator actually saw when a recording was refused for
/// lack of disk space. Every diagnosis this type can offer was being discarded
/// at the last step.
enum DeviceRecordingError: Error, Equatable, CustomStringConvertible, LocalizedError {
    case unsupportedSchemaVersion(Int)
    case invalidRecordingID
    case resolutionIsNotScoring(width: Int, height: Int)
    case emptyRecording
    case lossyRecording(lossCount: Int)
    case frameCountMismatch(declared: Int, indexed: Int)
    case missingFrame(String)
    case frameSizeMismatch(path: String, expected: Int, actual: Int)
    case framesDigestMismatch(expected: String, actual: String)
    case fileHashMismatch(path: String, expected: String, actual: String)
    case unsafeRelativePath(String)
    case missingRequiredRole(DeviceRecordingFileRole)
    case timestampRegression(path: String, previous: Int64, current: Int64)
    case malformedCSV(path: String, line: Int, reason: String)
    case intrinsicsCrossCheckFailed
    case insufficientFreeSpace(requiredBytes: Int64, availableBytes: Int64)

    var errorDescription: String? { description }

    var description: String {
        switch self {
        case .unsupportedSchemaVersion(let v): "unsupported device recording schema version \(v)"
        case .invalidRecordingID: "recording_id must not be empty"
        case .resolutionIsNotScoring(let w, let h):
            "recording is \(w)x\(h); only \(BenchResolution.scoring.width)x\(BenchResolution.scoring.height) may be scored"
        case .emptyRecording: "recording has no camera or IMU events"
        case .lossyRecording(let n):
            "recording declares \(n) losses; a lossy recording is invalid, not shorter"
        case .frameCountMismatch(let d, let i): "frame_count \(d) does not match \(i) indexed frames"
        case .missingFrame(let p): "missing frame file: \(p)"
        case .frameSizeMismatch(let p, let e, let a): "frame \(p) is \(a) bytes, expected \(e)"
        case .framesDigestMismatch(let e, let a): "frames digest mismatch: expected \(e), got \(a)"
        case .fileHashMismatch(let p, let e, let a): "SHA-256 mismatch for \(p): expected \(e), got \(a)"
        case .unsafeRelativePath(let p): "unsafe relative path: \(p)"
        case .missingRequiredRole(let r): "missing required file role: \(r.rawValue)"
        case .timestampRegression(let p, let prev, let cur): "timestamp regression in \(p): \(prev) -> \(cur)"
        case .malformedCSV(let p, let l, let r): "malformed CSV \(p):\(l): \(r)"
        case .intrinsicsCrossCheckFailed:
            "ARKit intrinsics disagree with the frozen upstream values scaled by 3"
        case .insufficientFreeSpace(let required, let available):
            String(
                format: "存储空间不足:本次录制需要 %.1f GiB(含余量),设备可用 %.1f GiB,还差 %.1f GiB。"
                    + "请清理空间,或改用更短的录制时长。",
                Double(required) / 1_073_741_824,
                Double(available) / 1_073_741_824,
                Double(max(0, required - available)) / 1_073_741_824
            )
        }
    }
}
