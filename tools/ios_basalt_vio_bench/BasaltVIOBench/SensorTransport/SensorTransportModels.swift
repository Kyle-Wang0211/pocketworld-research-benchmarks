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
        cameraWidth: Int32 = 640,
        cameraHeight: Int32 = 480,
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
    public let cameraHandoff: BoundedNonblockingHandoff<MonochromeCameraFrame>.Snapshot
    public let imuHandoff: BoundedNonblockingHandoff<PairedIMUSample>.Snapshot
    public let xrslamSensorHandoff: BoundedNonblockingHandoff<XRSLAMLiveSensorEvent>.Snapshot
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
