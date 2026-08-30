import XCTest
@testable import VIOReplacementBench

final class BenchModeTests: XCTestCase {
    func testOnlyApprovedModesExist() {
        XCTAssertEqual(BenchMode.allCases.map(\.rawValue), [
            "record", "live-soak", "replay-device-recording",
            "replay-paced", "replay-max"
        ])
    }

    /// EuRoC is the only channel with external ground truth. The device
    /// recording gives identical input to every arm, which makes them mutually
    /// comparable, but comparability is not ground truth.
    func testOnlyEuRoCCarriesExternalGroundTruth() {
        XCTAssertTrue(BenchMode.replayPaced.hasExternalGroundTruth)
        XCTAssertTrue(BenchMode.replayMax.hasExternalGroundTruth)
        XCTAssertFalse(BenchMode.replayDeviceRecording.hasExternalGroundTruth)
        XCTAssertFalse(BenchMode.record.hasExternalGroundTruth)
        XCTAssertFalse(BenchMode.liveSoak.hasExternalGroundTruth)
    }

    func testReplayModesDoNotOpenACamera() {
        XCTAssertTrue(BenchMode.replayDeviceRecording.isReplay)
        XCTAssertTrue(BenchMode.replayPaced.isReplay)
        XCTAssertTrue(BenchMode.replayMax.isReplay)
        XCTAssertFalse(BenchMode.record.isReplay)
        XCTAssertFalse(BenchMode.liveSoak.isReplay)
    }

    func testNativeBackendFailsClosedUntilRealCoreIsLinked() {
        #if PW_BASALT_CORE_LINKED
        XCTAssertEqual(basalt_bench_backend_available(), 1)
        #else
        XCTAssertEqual(basalt_bench_backend_available(), 0)
        #endif
    }
}

