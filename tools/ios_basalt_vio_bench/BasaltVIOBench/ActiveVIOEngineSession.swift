import Foundation

enum ActiveVIOEngineSessionError: LocalizedError {
    case queueFull
    case incompatibleInput(String)
    case operation(String, Error)

    var errorDescription: String? {
        switch self {
        case .queueFull:
            return "VIO 输入队列已满。"
        case .incompatibleInput(let detail):
            return "VIO 输入适配器不匹配：\(detail)"
        case .operation(let name, let error):
            return "VIO \(name) 失败：\(error.localizedDescription)"
        }
    }
}

/// One immutable engine selection per run. Basalt and XRSLAM live in separate
/// embedded dynamic frameworks so their pinned OpenCV versions never share a
/// link namespace. A session cannot change engine after creation.
final class ActiveVIOEngineSession {
    private enum Implementation {
        case basalt(BasaltNativeSession)
        case xrslam(XRSLAMNativeSession)
    }

    let backend: BenchBackend
    private let implementation: Implementation

    static func backendAvailable(_ backend: BenchBackend) -> Bool {
        switch backend {
        case .basalt: return basalt_bench_backend_available() == 1
        case .xrslam: return xrslam_bench_backend_available() == 1
        default: return false
        }
    }

    init(
        backend: BenchBackend,
        configURL: URL,
        calibrationURL: URL,
        imageWidth: Int,
        imageHeight: Int
    ) throws {
        self.backend = backend
        do {
            switch backend {
            case .basalt:
                implementation = .basalt(try BasaltNativeSession(
                    configURL: configURL,
                    calibrationURL: calibrationURL
                ))
            case .xrslam:
                implementation = .xrslam(try XRSLAMNativeSession(
                    configURL: configURL,
                    calibrationURL: calibrationURL,
                    imageWidth: imageWidth,
                    imageHeight: imageHeight
                ))
            default:
                throw ActiveVIOEngineSessionError.incompatibleInput(
                    "ARKit reference uses its isolated ARSession adapter"
                )
            }
        } catch {
            throw ActiveVIOEngineSessionError.operation("create", error)
        }
    }

    func submitIMU(_ sample: PairedIMUSample) throws {
        guard case .basalt(let session) = implementation else {
            throw ActiveVIOEngineSessionError.incompatibleInput(
                "XRSLAM requires separate raw events"
            )
        }
        try performBasalt("submit_paired_imu") { try session.submitIMU(sample) }
    }

    func submitIMU(_ event: RawIMUEvent) throws {
        guard case .xrslam(let session) = implementation else {
            throw ActiveVIOEngineSessionError.incompatibleInput(
                "Basalt requires gyro-driven paired IMU"
            )
        }
        try performXRSLAM("submit_raw_imu") { try session.submitIMU(event) }
    }

    func submitIMU(_ sample: EuRoCIMUSample) throws {
        switch implementation {
        case .basalt(let session):
            try performBasalt("submit_replay_imu") { try session.submitIMU(sample) }
        case .xrslam(let session):
            try performXRSLAM("submit_replay_imu") { try session.submitIMU(sample) }
        }
    }

    func submitCamera(
        _ frame: MonochromeCameraFrame,
        acceptedNanoseconds: UInt64
    ) throws {
        switch implementation {
        case .basalt(let session):
            try performBasalt("submit_live_camera") {
                try session.submitCamera(frame, acceptedNanoseconds: acceptedNanoseconds)
            }
        case .xrslam(let session):
            try performXRSLAM("submit_live_camera") {
                try session.submitCamera(frame, acceptedNanoseconds: acceptedNanoseconds)
            }
        }
    }

    /// Device-recording frames are raw luma planes with a `.y` extension; EuRoC
    /// frames are encoded images. The file *is* the plane in the first case, so
    /// there is nothing to decode and the only check that matters is that its
    /// length is exactly one frame.
    private static func loadReplayImage(
        _ url: URL,
        width: Int,
        height: Int
    ) throws -> GrayscaleImage {
        if url.pathExtension == "y" {
            return try RawLumaFrameLoader.load(
                url,
                format: DeviceRecordingCameraFormat(
                    width: width,
                    height: height,
                    pixelFormat: "luma8_from_420f_full_range",
                    nominalFPS: 30
                )
            )
        }
        return try GrayscaleImageLoader.load(
            url,
            expectedWidth: width,
            expectedHeight: height
        )
    }

    func submitReplayCamera(
        _ frame: EuRoCCameraFrame,
        acceptedNanoseconds: UInt64,
        width: Int,
        height: Int
    ) throws {
        let isRaw = frame.camera0ImageURL.pathExtension == "y"
        switch implementation {
        case .basalt(let session):
            let image: GrayscaleImage
            do {
                image = try Self.loadReplayImage(
                    frame.camera0ImageURL, width: width, height: height
                )
            } catch {
                throw ActiveVIOEngineSessionError.operation("decode_replay_camera", error)
            }
            try performBasalt("submit_replay_camera") {
                try session.submitCamera(
                    images: [image],
                    timestampNanoseconds: frame.timestampNanoseconds,
                    acceptedNanoseconds: acceptedNanoseconds
                )
            }
        case .xrslam(let session):
            // The pinned EuRoC path is kept byte-for-byte for the EuRoC channel;
            // a recorded raw plane has no file format for it to open, so it goes
            // through the same in-memory submission Basalt uses.
            if isRaw {
                let image = try Self.loadReplayImage(
                    frame.camera0ImageURL, width: width, height: height
                )
                try performXRSLAM("submit_device_recording_camera") {
                    try session.submitCamera(
                        images: [image],
                        timestampNanoseconds: frame.timestampNanoseconds,
                        acceptedNanoseconds: acceptedNanoseconds
                    )
                }
            } else {
                try performXRSLAM("submit_official_euroc_camera") {
                    try session.submitEuRoCCameraFile(
                        frame.camera0ImageURL,
                        timestampNanoseconds: frame.timestampNanoseconds,
                        acceptedNanoseconds: acceptedNanoseconds
                    )
                }
            }
        }
    }

    func pollPose() throws -> NativePoseSample? {
        switch implementation {
        case .basalt(let session):
            return try performBasalt("poll_pose") { try session.pollPose() }
        case .xrslam(let session):
            return try performXRSLAM("poll_pose") { try session.pollPose() }
        }
    }

    func snapshot() throws -> VIOEngineSnapshot {
        switch implementation {
        case .basalt(let session):
            return try performBasalt("snapshot") { try session.snapshot() }
        case .xrslam(let session):
            return try performXRSLAM("snapshot") { try session.snapshot() }
        }
    }

    func sealDrainStop() throws {
        switch implementation {
        case .basalt(let session):
            try performBasalt("seal_drain_stop") { try session.sealDrainStop() }
        case .xrslam(let session):
            try performXRSLAM("seal_drain_stop") { try session.sealDrainStop() }
        }
    }

    func requestStop() {
        switch implementation {
        case .basalt(let session): session.requestStop()
        case .xrslam(let session): session.requestStop()
        }
    }

    /// Releases the selected bridge handle before the process run lease is
    /// handed to another arm. Both concrete close operations are idempotent.
    func close() {
        switch implementation {
        case .basalt(let session): session.close()
        case .xrslam(let session): session.close()
        }
    }

    private func performBasalt<T>(
        _ name: String,
        _ body: () throws -> T
    ) throws -> T {
        do { return try body() }
        catch let error as BasaltNativeSessionError {
            if case .status(_, let code) = error, code == BASALT_BENCH_QUEUE_FULL {
                throw ActiveVIOEngineSessionError.queueFull
            }
            throw ActiveVIOEngineSessionError.operation(name, error)
        } catch {
            throw ActiveVIOEngineSessionError.operation(name, error)
        }
    }

    private func performXRSLAM<T>(
        _ name: String,
        _ body: () throws -> T
    ) throws -> T {
        do { return try body() }
        catch let error as XRSLAMNativeSessionError {
            if case .status(_, let code) = error, code == XRSLAM_BENCH_QUEUE_FULL {
                throw ActiveVIOEngineSessionError.queueFull
            }
            throw ActiveVIOEngineSessionError.operation(name, error)
        } catch {
            throw ActiveVIOEngineSessionError.operation(name, error)
        }
    }
}
