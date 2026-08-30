import ARKit
import AVFoundation
import CoreMotion
import Foundation
import QuartzCore
import simd

struct ARKitReferenceConfigurationReceipt: Equatable, Sendable {
    let autoFocusEnabled: Bool
    let worldAlignment: String
    let lightEstimationEnabled: Bool
    let horizontalPlaneDetectionEnabled: Bool
    let physicalMemoryBytes: UInt64
    let fourKMemoryThresholdBytes: UInt64
    let videoFormatMode: String
    let selectedWidth: Int
    let selectedHeight: Int
    let selectedFramesPerSecond: Int
    let selectedForHighResolutionCapture: Bool
    let thirtyFPSOverrideEnabled: Bool
    let delegateQueue: String
    let startOptions: String
}

struct ARKitReferenceLifecycleReceipt: Equatable, Sendable {
    var runRequestNanoseconds: UInt64?
    var runReturnNanoseconds: UInt64?
    var stopRequestNanoseconds: UInt64?
    var pauseReturnNanoseconds: UInt64?
    var lastCallbackNanoseconds: UInt64?
}

enum ARKitReferenceSessionError: LocalizedError {
    case unsupported
    case cameraPermissionDenied

    var errorDescription: String? {
        switch self {
        case .unsupported: return "ARWorldTrackingConfiguration is unsupported."
        case .cameraPermissionDenied: return "Camera permission is required for ARKit reference."
        }
    }
}

/// Dedicated reference adapter. It owns the only ARSession for an ARKit run and
/// has no reference to either C++ engine or their sensor transports.
final class ARKitReferenceSession: NSObject, ARSessionDelegate, @unchecked Sendable {
    private(set) var accounting: ARKitReferenceAccounting!
    private let session = ARSession()

    /// Display-only tap on frames this adapter has already handled.
    ///
    /// The session is deliberately never exposed: assigning an ARSession to an
    /// ARSCNView makes that view the session's delegate, which would displace
    /// this adapter and silently stop `didUpdate` -- accounting would stall and a
    /// `record` run would persist nothing while the screen looked healthy.
    var previewTap: PreviewFrameTap?
    private(set) var configurationReceipt: ARKitReferenceConfigurationReceipt?
    private let startMonotonicSeconds: Double
    private let lifecycleLock = NSLock()
    private var lifecycleValue = ARKitReferenceLifecycleReceipt()
    private var paused = false

    /// Set only for `record` runs. When present, the frames ARKit is tracking on
    /// are persisted so every candidate arm can later be fed the identical
    /// input. iOS grants the rear camera to one session, so recording from
    /// ARKit's own frames is the only way one capture serves all three arms.
    var recorder: DeviceRecordingWriter?
    private var recorderFailure: Error?

    /// ARKit exposes no raw inertial stream, so a recording that only captured
    /// ARFrames carried zero IMU samples -- and a visual-inertial candidate
    /// replaying it would have had no inertial data at all, which is also where
    /// its metric scale comes from. CoreMotion runs alongside the session,
    /// independent of the camera, for exactly this.
    private let motion = CMMotionManager()
    private let motionQueue = OperationQueue()

    init(startMonotonicSeconds: Double = CACurrentMediaTime()) {
        self.startMonotonicSeconds = startMonotonicSeconds
        super.init()
    }

    func start() throws {
        guard ARWorldTrackingConfiguration.isSupported else {
            throw ARKitReferenceSessionError.unsupported
        }
        guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
            throw ARKitReferenceSessionError.cameraPermissionDenied
        }
        try onMainSync {
            let configuration = ARWorldTrackingConfiguration()
            configuration.isAutoFocusEnabled = true
            configuration.worldAlignment = .gravity
            configuration.isLightEstimationEnabled = false
            configuration.planeDetection = [.horizontal]

            let physicalMemory = ProcessInfo.processInfo.physicalMemory
            let fourKThreshold: UInt64 = 5_000_000_000
            guard #available(iOS 16.0, *) else {
                throw ARKitReferenceSessionError.unsupported
            }
            guard let highResolution43 = ARWorldTrackingConfiguration.supportedVideoFormats
                .filter({
                    Int($0.imageResolution.width) == 1920
                        && Int($0.imageResolution.height) == 1440
                        && $0.isRecommendedForHighResolutionFrameCapturing
                })
                .max(by: { $0.framesPerSecond < $1.framesPerSecond }) else {
                throw ARKitReferenceSessionError.unsupported
            }
            configuration.videoFormat = highResolution43
            let thirtyFPSOverride = ProcessInfo.processInfo.environment[
                "OFFICIAL_AETHER_AR_30FPS"
            ] == "1"
            if thirtyFPSOverride,
               let thirty = ARWorldTrackingConfiguration.supportedVideoFormats.first(where: {
                   $0.imageResolution == configuration.videoFormat.imageResolution
                       && $0.framesPerSecond == 30
                       && $0.isRecommendedForHighResolutionFrameCapturing
                           == configuration.videoFormat.isRecommendedForHighResolutionFrameCapturing
               }) {
                configuration.videoFormat = thirty
            }

            let selected = configuration.videoFormat
            accounting = ARKitReferenceAccounting(
                startMonotonicSeconds: startMonotonicSeconds,
                nominalFramesPerSecond: Double(selected.framesPerSecond)
            )
            configurationReceipt = ARKitReferenceConfigurationReceipt(
                autoFocusEnabled: configuration.isAutoFocusEnabled,
                worldAlignment: "gravity",
                lightEstimationEnabled: configuration.isLightEstimationEnabled,
                horizontalPlaneDetectionEnabled: configuration.planeDetection.contains(.horizontal),
                physicalMemoryBytes: physicalMemory,
                fourKMemoryThresholdBytes: fourKThreshold,
                videoFormatMode: "hires43",
                selectedWidth: Int(selected.imageResolution.width),
                selectedHeight: Int(selected.imageResolution.height),
                selectedFramesPerSecond: selected.framesPerSecond,
                selectedForHighResolutionCapture: {
                    if #available(iOS 16.0, *) {
                        return selected.isRecommendedForHighResolutionFrameCapturing
                    }
                    return false
                }(),
                thirtyFPSOverrideEnabled: thirtyFPSOverride,
                delegateQueue: "com.apple.main-thread",
                startOptions: "resetTracking,removeExistingAnchors"
            )
            session.delegateQueue = .main
            session.delegate = self
            lifecycleLock.withLock {
                lifecycleValue.runRequestNanoseconds = DispatchTime.now().uptimeNanoseconds
            }
            session.run(configuration, options: [.resetTracking, .removeExistingAnchors])
            lifecycleLock.withLock {
                lifecycleValue.runReturnNanoseconds = DispatchTime.now().uptimeNanoseconds
            }
        }
    }

    func pause() {
        stopMotionRecording()
        let shouldPause = lifecycleLock.withLock { () -> Bool in
            guard !paused else { return false }
            paused = true
            lifecycleValue.stopRequestNanoseconds = DispatchTime.now().uptimeNanoseconds
            return true
        }
        guard shouldPause else { return }
        onMainSync {
            // Detach first. ARKit can deliver an in-flight frame between
            // markPaused() and the delegate being cleared, and every such frame
            // was counted as a callback-after-pause and invalidated the run --
            // which killed an otherwise clean recording. Clearing the delegate
            // before anything else makes further delivery impossible rather than
            // merely unlikely.
            session.delegate = nil
            accounting?.markPaused()
            session.pause()
            lifecycleLock.withLock {
                lifecycleValue.pauseReturnNanoseconds = DispatchTime.now().uptimeNanoseconds
                lifecycleValue.lastCallbackNanoseconds =
                    accounting?.snapshot().lastCallbackNanoseconds
            }
        }
    }

    func lifecycleReceipt() -> ARKitReferenceLifecycleReceipt {
        lifecycleLock.withLock { lifecycleValue }
    }

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        let handlerStart = CACurrentMediaTime()
        let transform = frame.camera.transform
        let q = simd_quatf(transform)
        let timestampNS = Int64((frame.timestamp * 1_000_000_000).rounded())
        let pose = TimedPose(
            timestampNanoseconds: timestampNS,
            translation: Vector3(
                x: Double(transform.columns.3.x),
                y: Double(transform.columns.3.y),
                z: Double(transform.columns.3.z)
            ),
            rotation: Quaternion(
                w: Double(q.real),
                x: Double(q.imag.x),
                y: Double(q.imag.y),
                z: Double(q.imag.z)
            )
        )
        accounting?.recordFrame(
            timestampSeconds: frame.timestamp,
            callbackSeconds: handlerStart,
            pose: pose,
            tracking: Self.trackingEvidence(frame.camera.trackingState),
            mapping: Self.mappingEvidence(frame.worldMappingStatus)
        )
        // frame.timestamp is in the CACurrentMediaTime domain, which is
        // mach_absolute_time -- the bench's single canonical domain. No
        // conversion, and deliberately no std::chrono anywhere near it.
        if let recorder {
            do {
                try recorder.recordIntrinsicsIfNeeded(
                    CameraIntrinsics(
                        fx: Double(frame.camera.intrinsics.columns.0.x),
                        fy: Double(frame.camera.intrinsics.columns.1.y),
                        cx: Double(frame.camera.intrinsics.columns.2.x),
                        cy: Double(frame.camera.intrinsics.columns.2.y)
                    )
                )
                recorder.appendFrame(
                    pixelBuffer: frame.capturedImage,
                    timestampNanoseconds: timestampNS
                )
                recorder.appendARKitPose(
                    timestampNanoseconds: timestampNS,
                    tumRow: Self.tumRow(timestampNanoseconds: timestampNS, pose: pose)
                )
            } catch {
                // A failed cross-check must stop the capture immediately rather
                // than let the operator spend five minutes producing frames no
                // arm may be scored on.
                if recorderFailure == nil { recorderFailure = error }
                self.recorder = nil
            }
        }
        startMotionRecordingIfNeeded()
        previewTap?.offer(
            pixelBuffer: frame.capturedImage,
            monotonicNanoseconds: UInt64(max(0, timestampNS))
        )
        // Recording and preview costs are inside the measured handler duration on
        // purpose: the
        // ARKit arm really does pay it, and hiding it would flatter ARKit
        // against candidates that replay from disk.
        accounting?.recordHandlerDuration(
            milliseconds: (CACurrentMediaTime() - handlerStart) * 1_000
        )
    }

    /// TUM: `timestamp tx ty tz qx qy qz qw`.
    static func tumRow(timestampNanoseconds: Int64, pose: TimedPose) -> String {
        let seconds = timestampNanoseconds / 1_000_000_000
        let remainder = timestampNanoseconds % 1_000_000_000
        return String(
            format: "%lld.%09lld %.9f %.9f %.9f %.9f %.9f %.9f %.9f",
            seconds, remainder,
            pose.translation.x, pose.translation.y, pose.translation.z,
            pose.rotation.x, pose.rotation.y, pose.rotation.z, pose.rotation.w
        )
    }

    /// Surfaced by the coordinator so a recorder failure invalidates the run.
    func recordingFailure() -> Error? { recorderFailure }

    /// Streams raw gyroscope and accelerometer into the recording.
    ///
    /// Gyroscope timestamps drive the pairing, matching the transport's
    /// `basaltGyroDrivenPaired` mode and Basalt's own rs_t265 device, so a
    /// replayed recording pairs the way a live run does. Acceleration is
    /// converted to m/s^2 with the same -9.80665 factor XRSLAM's iOS sample
    /// applies, so both engines receive the convention their upstream expects.
    ///
    /// `deviceMotion` is deliberately not used: it returns a fused, gravity-
    /// removed estimate, which is another estimator's output rather than the raw
    /// inertial measurement a VIO front end integrates.
    private func startMotionRecordingIfNeeded() {
        guard recorder != nil, !motion.isGyroActive else { return }
        motionQueue.maxConcurrentOperationCount = 1
        motion.gyroUpdateInterval = 1.0 / 100.0
        motion.accelerometerUpdateInterval = 1.0 / 100.0
        motion.startAccelerometerUpdates()
        motion.startGyroUpdates(to: motionQueue) { [weak self] data, _ in
            guard let self, let data, let recorder = self.recorder else { return }
            guard let accel = self.motion.accelerometerData else { return }
            // CoreMotion reports seconds on the same mach_absolute_time base the
            // rest of the bench uses.
            let timestampNS = Int64((data.timestamp * 1_000_000_000).rounded())
            recorder.appendIMU(
                timestampNanoseconds: timestampNS,
                gyroscope: (
                    data.rotationRate.x, data.rotationRate.y, data.rotationRate.z
                ),
                acceleration: (
                    accel.acceleration.x * -9.80665,
                    accel.acceleration.y * -9.80665,
                    accel.acceleration.z * -9.80665
                )
            )
        }
    }

    private func stopMotionRecording() {
        if motion.isGyroActive { motion.stopGyroUpdates() }
        if motion.isAccelerometerActive { motion.stopAccelerometerUpdates() }
    }

    func session(_ session: ARSession, didFailWithError error: Error) {
        accounting?.recordFailure()
    }

    func sessionWasInterrupted(_ session: ARSession) {
        accounting?.recordInterruption()
    }

    func sessionInterruptionEnded(_ session: ARSession) {
        accounting?.recordInterruptionEnded()
    }

    private static func trackingEvidence(
        _ state: ARCamera.TrackingState
    ) -> ARKitTrackingEvidence {
        switch state {
        case .normal: return .normal
        case .notAvailable: return .notAvailable
        case .limited(let reason):
            switch reason {
            case .initializing: return .limitedInitializing
            case .excessiveMotion: return .limitedExcessiveMotion
            case .insufficientFeatures: return .limitedInsufficientFeatures
            case .relocalizing: return .limitedRelocalizing
            @unknown default: return .limitedOther
            }
        }
    }

    private static func mappingEvidence(
        _ state: ARFrame.WorldMappingStatus
    ) -> ARKitMappingEvidence {
        switch state {
        case .notAvailable: return .notAvailable
        case .limited: return .limited
        case .extending: return .extending
        case .mapped: return .mapped
        @unknown default: return .notAvailable
        }
    }

    private func onMainSync(_ body: () -> Void) {
        if Thread.isMainThread { body() } else { DispatchQueue.main.sync(execute: body) }
    }

    private func onMainSync(_ body: () throws -> Void) rethrows {
        if Thread.isMainThread { try body() } else { try DispatchQueue.main.sync(execute: body) }
    }
}
