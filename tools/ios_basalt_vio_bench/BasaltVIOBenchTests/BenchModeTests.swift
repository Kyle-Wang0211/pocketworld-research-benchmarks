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


/// Pins the mode/channel classification that four separate guards got wrong.
///
/// Each was written when `liveSoak` was the only live mode, so each used it as a
/// synonym for "runs a camera". Adding `record` therefore made preparation
/// reject it as a replay, made the view model skip camera permission, and would
/// have failed receipt validation twice. The bug recurred three times because it
/// was fixed one call site at a time.
final class BenchModeClassificationTests: XCTestCase {

    func testRecordIsLiveNotReplay() {
        XCTAssertFalse(BenchMode.record.isReplay)
        XCTAssertFalse(BenchMode.liveSoak.isReplay)
        XCTAssertTrue(BenchMode.replayDeviceRecording.isReplay)
        XCTAssertTrue(BenchMode.replayPaced.isReplay)
        XCTAssertTrue(BenchMode.replayMax.isReplay)
    }

    func testChannelClassificationMatchesModes() {
        XCTAssertFalse(RunReceiptChannel.record.isReplay)
        XCTAssertFalse(RunReceiptChannel.liveSoak.isReplay)
        XCTAssertTrue(RunReceiptChannel.replayDeviceRecording.isReplay)
        XCTAssertTrue(RunReceiptChannel.replayPaced.isReplay)
        XCTAssertTrue(RunReceiptChannel.replayMax.isReplay)
    }

    /// Every mode must be classified. A new case that forgets to answer this is
    /// exactly how the previous three recurrences happened.
    func testEveryModeAndChannelIsClassified() {
        XCTAssertEqual(BenchMode.allCases.count, 5)
        XCTAssertEqual(RunReceiptChannel.allCases.count, 5)
        XCTAssertEqual(
            BenchMode.allCases.filter(\.isReplay).count,
            RunReceiptChannel.allCases.filter(\.isReplay).count,
            "modes and channels must agree on how many are replays"
        )
    }
}
