import XCTest
@testable import VIOReplacementBench

final class SensorTransportAccountingTests: XCTestCase {
    func testBenchmarkConfigurationFreezesRequestedSensorRatesAndResolution() {
        let configuration = SensorTransportConfiguration.benchmark

        XCTAssertEqual(configuration.cameraWidth, 640)
        XCTAssertEqual(configuration.cameraHeight, 480)
        XCTAssertEqual(configuration.cameraRateHz, 30)
        XCTAssertEqual(configuration.motionRateHz, 100)
    }

    func testPinnedXRSLAMAccelerationScaleAndAxes() {
        let converted = CoreMotionIMUConversion.accelerationMetersPerSecondSquared(
            timestampNanoseconds: 123,
            xInG: 1,
            yInG: -2,
            zInG: 0.5
        )

        XCTAssertEqual(converted.timestampNanoseconds, 123)
        XCTAssertEqual(converted.x, -9.80665, accuracy: 1e-12)
        XCTAssertEqual(converted.y, 19.61330, accuracy: 1e-12)
        XCTAssertEqual(converted.z, -4.903325, accuracy: 1e-12)
    }

    func testPinnedXRSLAMGyroscopeAxesRemainUnchanged() {
        let converted = CoreMotionIMUConversion.gyroscopeRadiansPerSecond(
            timestampNanoseconds: 456,
            x: 1,
            y: -2,
            z: 0.5
        )

        XCTAssertEqual(
            converted,
            MotionVectorSample(timestampNanoseconds: 456, x: 1, y: -2, z: 0.5)
        )
    }

    func testInputDropInterruptionAndRegressionCountersAreIndependent() {
        let accounting = SensorTransportAccounting()

        accounting.recordCameraInput()
        accounting.recordCameraInput()
        accounting.recordCameraDrop(.late)
        accounting.recordCameraDrop(.outOfBuffers)
        accounting.recordCameraDrop(.discontinuity)
        accounting.recordCameraDrop(.invalidFormat)
        accounting.recordCameraDrop(.timestampRegression)
        accounting.recordGyroscopeInput()
        accounting.recordAccelerometerInput()
        accounting.recordMotionError()
        accounting.recordCaptureInterruption()
        accounting.recordCaptureRuntimeError()

        let snapshot = accounting.snapshot()
        XCTAssertEqual(snapshot.cameraInputs, 2)
        XCTAssertEqual(snapshot.cameraDropsLate, 1)
        XCTAssertEqual(snapshot.cameraDropsOutOfBuffers, 1)
        XCTAssertEqual(snapshot.cameraDropsDiscontinuity, 1)
        XCTAssertEqual(snapshot.cameraDropsInvalidFormat, 1)
        XCTAssertEqual(snapshot.timestampRegressions, 1)
        XCTAssertEqual(snapshot.gyroscopeInputs, 1)
        XCTAssertEqual(snapshot.accelerometerInputs, 1)
        XCTAssertEqual(snapshot.motionErrors, 1)
        XCTAssertEqual(snapshot.captureInterruptions, 1)
        XCTAssertEqual(snapshot.captureRuntimeErrors, 1)
        XCTAssertEqual(snapshot.totalCameraDrops, 5)
    }
}
