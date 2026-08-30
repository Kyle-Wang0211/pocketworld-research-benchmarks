import XCTest
@testable import VIOReplacementBench

final class BenchmarkTimingTests: XCTestCase {
    func testLiveRunMatchesFiveMinuteProductSessionLimit() {
        XCTAssertEqual(LiveBenchmarkDuration.warmupNanoseconds, 0)
        XCTAssertEqual(LiveBenchmarkDuration.measurementNanoseconds, 300_000_000_000)
        XCTAssertEqual(LiveBenchmarkDuration.totalNanoseconds, 300_000_000_000)
    }

    func testMeasurementWindowUsesCaptureTimeAndHalfOpenBounds() {
        let window = BenchmarkMeasurementWindow(
            startNanoseconds: 0,
            endNanoseconds: 300_000_000_000
        )
        XCTAssertTrue(window.contains(captureNanoseconds: 0))
        XCTAssertTrue(window.contains(captureNanoseconds: 299_999_999_999))
        XCTAssertFalse(window.contains(captureNanoseconds: 300_000_000_000))
    }

    func testTUMTimestampPreservesNanosecondsExactly() {
        XCTAssertEqual(
            TUMTimestampFormatter.string(nanoseconds: 1_403_636_579_764_355_558),
            "1403636579.764355558"
        )
        XCTAssertEqual(TUMTimestampFormatter.string(nanoseconds: 1), "0.000000001")
    }
}
