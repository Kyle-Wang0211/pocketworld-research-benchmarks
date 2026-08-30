import XCTest
@testable import VIOReplacementBench

final class RawIMUDeliveryTests: XCTestCase {
    func testRawEventPreservesSensorKindTimestampAndUpstreamInputUnits() {
        let acceleration = MotionVectorSample(
            timestampNanoseconds: 10,
            x: 1,
            y: -2,
            z: 0.5
        )
        let gyroscope = CoreMotionIMUConversion.gyroscopeRadiansPerSecond(
            timestampNanoseconds: 11,
            x: 0.1,
            y: 0.2,
            z: 0.3
        )

        XCTAssertEqual(RawIMUEvent.acceleration(acceleration).timestampNanoseconds, 10)
        XCTAssertEqual(RawIMUEvent.gyroscope(gyroscope).timestampNanoseconds, 11)
        XCTAssertEqual(acceleration.x, 1, accuracy: 1e-12)
        XCTAssertEqual(gyroscope.z, 0.3, accuracy: 1e-12)
    }

    func testBenchBackendSelectsTheOnlyPermittedLiveIMUDelivery() {
        XCTAssertEqual(IMUDeliveryMode.forBackend(.basalt), .basaltGyroDrivenPaired)
        XCTAssertEqual(IMUDeliveryMode.forBackend(.xrslam), .xrslamRawSeparateEvents)
    }
}
