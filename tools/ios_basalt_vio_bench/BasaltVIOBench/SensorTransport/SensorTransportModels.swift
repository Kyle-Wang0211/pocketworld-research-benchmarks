import CoreVideo
import Foundation

public struct SensorTransportConfiguration: Equatable, Sendable {
    public let cameraWidth: Int32
    public let cameraHeight: Int32
    public let cameraRateHz: Int32
    public let motionRateHz: Double
    public let cameraQueueCapacity: Int
    public let imuQueueCapacity: Int
    public let pendingGyroscopeCapacity: Int

    public init(
        // The candidate arms capture at the diagnostic resolution, not the
        // scoring one, and that is not a shortfall -- it is the architecture.
        //
        // Under contract v2 Basalt and XRSLAM are scored by replaying the ARKit
        // recording at 1920x1440, where the intrinsics come from
        // ARFrame.camera.intrinsics: measured for exactly those frames. A live
        // candidate run has no ARSession, so no measured intrinsics exist for it.
        //
        // Raising this to 1920x1440 on 2026-08-30 broke the arm outright: the
        // frozen calibration still declares [[640, 480]], and Basalt correctly
        // refused every frame with invalid_argument
        // (plane.width != resolution.x()). Unblocking it would have meant
        // inventing intrinsics by scaling the upstream values threefold -- and
        // that is only valid if both formats share a field of view, which cannot
        // be shown from the artifacts on hand. Fabricating a calibration to
        // unblock a run the contract already marks non-scoring is a bad trade.
        //
        // So live capture stays at the frozen, upstream-verified 640x480 pairing
        // and is used for what it can answer: transport, clock domain, loss and
        // stop semantics. Resolution pressure at 1920x1440 is answered by the
        // replay channel, on measured intrinsics.
        cameraWidth: Int32 = Int32(BenchResolution.diagnostic.width),
        cameraHeight: Int32 = Int32(BenchResolution.diagnostic.height),
        cameraRateHz: Int32 = 30,
        motionRateHz: Double = 100,
        cameraQueueCapacity: Int = 8,
        imuQueueCapacity: Int = 128,
        pendingGyroscopeCapacity: Int = 128
    ) {
        precondition(cameraWidth > 0 && cameraHeight > 0)
        precondition(cameraRateHz > 0 && motionRateHz > 0)
        precondition(cameraQueueCapacity > 0 && imuQueueCapacity > 0)
        precondition(pendingGyroscopeCapacity > 0)
        self.cameraWidth = cameraWidth
        self.cameraHeight = cameraHeight
        self.cameraRateHz = cameraRateHz
        self.motionRateHz = motionRateHz
        self.cameraQueueCapacity = cameraQueueCapacity
        self.imuQueueCapacity = imuQueueCapacity
        self.pendingGyroscopeCapacity = pendingGyroscopeCapacity
    }

    public static let benchmark = SensorTransportConfiguration()

    /// The production capture size. Selected by `-PWLiveFullResolution`; see
    /// BenchResolution.liveFullResolutionRequested for why the frozen 640x480
    /// pairing is no longer the only defensible live configuration.
    /// 60 Hz, not 30: production's nominal rate is 60 and drops to 30 only
    /// under thermal pressure. At 30 the camera, not the engine, sets the
    /// ceiling -- both tracker_frequent settings processed every frame the
    /// camera delivered and reported ~30 fps, which says nothing about how fast
    /// the engine could go. Comparing against ARKit's measured 56.7 fps needs
    /// the camera to offer more than 56.7.
    public static let productionResolution = SensorTransportConfiguration(
        cameraWidth: Int32(BenchResolution.scoring.width),
        cameraHeight: Int32(BenchResolution.scoring.height),
        cameraRateHz: 30
    )

    public static var live: SensorTransportConfiguration {
        let base: SensorTransportConfiguration = BenchResolution.liveFullResolutionRequested ? .productionResolution : .benchmark
        // [bench 2026-09-04] `-PWLiveCameraRate N` overrides the live camera rate (60 = production's nominal rate; the
        // receipt's active-format fields record what actually ran). Without the flag: byte-equivalent to before.
        let args = ProcessInfo.processInfo.arguments
        if let i = args.firstIndex(of: "-PWLiveCameraRate"), i + 1 < args.count, let hz = Int32(args[i + 1]), hz > 0, hz <= 240 {
            return SensorTransportConfiguration(cameraWidth: base.cameraWidth, cameraHeight: base.cameraHeight, cameraRateHz: hz, motionRateHz: base.motionRateHz,
                                                cameraQueueCapacity: base.cameraQueueCapacity, imuQueueCapacity: base.imuQueueCapacity, pendingGyroscopeCapacity: base.pendingGyroscopeCapacity)
        }
        return base
    }
}

/// A retained camera buffer whose plane zero is the 8-bit monochrome luma
/// image. Consumers must treat the pixel buffer as read-only. The callback does
/// not copy, scale, encode, render, or write this buffer.
public struct MonochromeCameraFrame: @unchecked Sendable {
    public let timestampNanoseconds: UInt64
    public let pixelBuffer: CVPixelBuffer
    public let width: Int
    public let height: Int
    public let lumaPlaneIndex: Int

    public init(
        timestampNanoseconds: UInt64,
        pixelBuffer: CVPixelBuffer,
        width: Int,
        height: Int,
        lumaPlaneIndex: Int = 0
    ) {
        self.timestampNanoseconds = timestampNanoseconds
        self.pixelBuffer = pixelBuffer
        self.width = width
        self.height = height
        self.lumaPlaneIndex = lumaPlaneIndex
    }
}

/// One sensor vector. Core Motion gyroscope values are radians/second. Live
/// transport converts Core Motion accelerometer G values to m/s^2 before IMU
/// assembly. Pairing is the pinned upstream transport rule, not a VIO choice.
public struct MotionVectorSample: Equatable, Sendable {
    public let timestampNanoseconds: UInt64
    public let x: Double
    public let y: Double
    public let z: Double

    public init(timestampNanoseconds: UInt64, x: Double, y: Double, z: Double) {
        self.timestampNanoseconds = timestampNanoseconds
        self.x = x
        self.y = y
        self.z = z
    }
}

/// Selects only the transport adapter required by the frozen engine. Hardware
/// capture stays shared; the estimator-specific conversion happens after the
/// same Core Motion callbacks have produced SI-valued samples.
public enum IMUDeliveryMode: String, Equatable, Sendable {
    case basaltGyroDrivenPaired = "basalt_gyro_driven_paired"
    case xrslamRawSeparateEvents = "xrslam_raw_separate_events"

    static func forBackend(_ backend: BenchBackend) -> IMUDeliveryMode {
        backend == .xrslam ? .xrslamRawSeparateEvents : .basaltGyroDrivenPaired
    }
}

/// XRSLAM's official mobile adapter accepts accelerometer and gyroscope events
/// as distinct timestamped records. Acceleration stays in Core Motion G until
/// the frozen XRSLAM bridge multiplies it by -9.80665; gyroscope values are
/// radians/second. No interpolation or synthetic pairing is permitted here.
public enum RawIMUEvent: Equatable, Sendable {
    case acceleration(MotionVectorSample)
    case gyroscope(MotionVectorSample)

    public var timestampNanoseconds: UInt64 {
        switch self {
        case .acceleration(let sample), .gyroscope(let sample):
            return sample.timestampNanoseconds
        }
    }

    public var sample: MotionVectorSample {
        switch self {
        case .acceleration(let sample), .gyroscope(let sample):
            return sample
        }
    }
}

/// One callback-order-preserving ingress used only by the XRSLAM arm. Camera,
/// accelerometer, and gyroscope callbacks execute on the same serial queue and
/// enter this one bounded handoff, matching the official iOS transport order.
public enum XRSLAMLiveSensorEvent: @unchecked Sendable {
    case camera(MonochromeCameraFrame)
    case imu(RawIMUEvent)
}

/// Frozen unit/axis convention paired with the selected iPhone 14 Pro
/// calibration. Source: `openxrlab/xrslam` revision
/// `4beb1a942f33da9afbfae2d70e2c641cfc2bb675`,
/// `xrslam-ios/visualizer/src/Motion.swift:3,57`: acceleration uses
/// `GRAVITY_NOMINAL = -9.80665`; gyro x/y/z pass through unchanged.
public enum CoreMotionIMUConversion {
    public static let metersPerSecondSquaredPerG = -9.80665

    public static func accelerationMetersPerSecondSquared(
        timestampNanoseconds: UInt64,
        xInG: Double,
        yInG: Double,
        zInG: Double
    ) -> MotionVectorSample {
        MotionVectorSample(
            timestampNanoseconds: timestampNanoseconds,
            x: xInG * metersPerSecondSquaredPerG,
            y: yInG * metersPerSecondSquaredPerG,
            z: zInG * metersPerSecondSquaredPerG
        )
    }

    public static func gyroscopeRadiansPerSecond(
        timestampNanoseconds: UInt64,
        x: Double,
        y: Double,
        z: Double
    ) -> MotionVectorSample {
        MotionVectorSample(timestampNanoseconds: timestampNanoseconds, x: x, y: y, z: z)
    }
}

public struct LiveSensorTransportSnapshot: Equatable, Sendable {
    public let state: SensorTransportLifecycle.State
    public let accounting: SensorTransportAccountingSnapshot
    public let imuDeliveryMode: IMUDeliveryMode
    public let imuAssembly: IMUAssemblyReceipt
    public let cameraHandoff: BoundedSensorHandoff<MonochromeCameraFrame>.Snapshot
    public let imuHandoff: BoundedSensorHandoff<PairedIMUSample>.Snapshot
    public let xrslamSensorHandoff: BoundedSensorHandoff<XRSLAMLiveSensorEvent>.Snapshot
    public let captureFormat: LiveCaptureFormatReceipt?
}

public struct LiveCaptureFormatReceipt: Equatable, Sendable {
    public let cameraDeviceType: String
    public let activeFormatIndex: Int
    public let activeFormatMediaSubtype: String
    public let outputPixelFormat: String
    public let width: Int32
    public let height: Int32
    public let selectedFramesPerSecond: Int32
    public let supportedFrameRateRange: String
    public let fieldOfViewDegrees: Double
    public let zoomFactor: Double
    public let rotationDegrees: Double
    public let preferredStabilizationMode: Int
    public let activeStabilizationMode: Int
    public let sessionPreset: String
    /// How many device formats satisfied the frozen requirements. Recorded
    /// because selection among several is a weaker identity than a unique match,
    /// and a reader must be able to tell which one this run had.
    public let matchingFormatCount: Int
    public let grayscaleConversion: String
    public let xrslamPixelPipelineDivergence: String

    public static func fourCC(_ value: OSType) -> String {
        let scalars = [24, 16, 8, 0].map { shift -> UnicodeScalar in
            let byte = UInt8(truncatingIfNeeded: value >> OSType(shift))
            return UnicodeScalar(byte >= 32 && byte <= 126 ? byte : 46)
        }
        return String(String.UnicodeScalarView(scalars))
    }
}
