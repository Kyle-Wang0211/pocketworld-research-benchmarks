import XCTest
@testable import VIOReplacementBench

final class MonotonicClockMapperTests: XCTestCase {
    func testMapsCameraAndMotionIntoTheSameMonotonicDomain() throws {
        let mapper = MonotonicClockMapper(
            cameraHostTimeAnchorSeconds: 400.0,
            coreMotionUptimeAnchorSeconds: 100.0,
            monotonicAnchorNanoseconds: 9_000_000_000
        )

        XCTAssertEqual(try mapper.cameraNanoseconds(hostTimeSeconds: 400.025), 9_025_000_000)
        XCTAssertEqual(try mapper.motionNanoseconds(uptimeSeconds: 100.025), 9_025_000_000)
    }

    func testMapsSamplesBeforeTheAnchorWithoutWrapping() throws {
        let mapper = MonotonicClockMapper(
            cameraHostTimeAnchorSeconds: 20.0,
            coreMotionUptimeAnchorSeconds: 10.0,
            monotonicAnchorNanoseconds: 5_000_000_000
        )

        XCTAssertEqual(try mapper.cameraNanoseconds(hostTimeSeconds: 19.5), 4_500_000_000)
        XCTAssertEqual(try mapper.motionNanoseconds(uptimeSeconds: 9.5), 4_500_000_000)
    }

    func testRejectsInvalidAndOutOfRangeInputs() {
        let mapper = MonotonicClockMapper(
            cameraHostTimeAnchorSeconds: 1.0,
            coreMotionUptimeAnchorSeconds: 1.0,
            monotonicAnchorNanoseconds: 10
        )

        XCTAssertThrowsError(try mapper.cameraNanoseconds(hostTimeSeconds: .nan))
        XCTAssertThrowsError(try mapper.motionNanoseconds(uptimeSeconds: -1.0))
    }

    func testTimestampSequenceDetectsRegressionWithoutAdvancingWatermark() {
        var sequence = TimestampSequenceValidator()

        XCTAssertEqual(sequence.observe(100), .accepted)
        XCTAssertEqual(sequence.observe(100), .regression(previous: 100, received: 100))
        XCTAssertEqual(sequence.observe(99), .regression(previous: 100, received: 99))
        XCTAssertEqual(sequence.observe(101), .accepted)
        XCTAssertEqual(sequence.regressionCount, 2)
        XCTAssertEqual(sequence.lastAcceptedTimestamp, 101)
    }
}
