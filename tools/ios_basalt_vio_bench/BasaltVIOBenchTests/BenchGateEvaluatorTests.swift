import XCTest
@testable import VIOReplacementBench

final class BenchGateEvaluatorTests: XCTestCase {
    func testLiveGateCanScaleWithTheFrozenSelectedFormatRate() {
        let verdict = BenchGateEvaluator.live(
            firstUsablePoseLatencyMilliseconds: 500,
            processedFPS: 29,
            p95LatencyMilliseconds: 10,
            appDropRate: 0,
            thermalCriticalSeconds: 0,
            thermalSeriousSeconds: 0,
            peakFootprintMB: 100,
            finitePoseRatio: 1,
            processedFPSMinimum: 54
        )
        XCTAssertFalse(verdict.passed)
        XCTAssertTrue(verdict.failedReasons.contains("processed_fps<54.0"))
    }
    func testLiveThresholdsAreInclusive() {
        let verdict = BenchGateEvaluator.live(
            firstUsablePoseLatencyMilliseconds: 1_800,
            processedFPS: 27,
            p95LatencyMilliseconds: 66.7,
            appDropRate: 0,
            thermalCriticalSeconds: 0,
            thermalSeriousSeconds: 0,
            peakFootprintMB: 750,
            finitePoseRatio: 0.995
        )
        XCTAssertTrue(verdict.passed)
    }

    func testLiveReportsEveryFailedGate() {
        let verdict = BenchGateEvaluator.live(
            firstUsablePoseLatencyMilliseconds: 1_800.1,
            processedFPS: 26,
            p95LatencyMilliseconds: 70,
            appDropRate: 0.02,
            thermalCriticalSeconds: 1,
            thermalSeriousSeconds: 2,
            peakFootprintMB: 800,
            finitePoseRatio: 0.9
        )
        XCTAssertFalse(verdict.passed)
        XCTAssertEqual(verdict.failedReasons.count, 8)
        XCTAssertTrue(
            verdict.failedReasons.contains("first_usable_pose_latency_ms>1800.0")
        )
    }
}
