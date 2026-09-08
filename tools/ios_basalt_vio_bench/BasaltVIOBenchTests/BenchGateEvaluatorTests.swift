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
            firstUsablePoseLatencyMilliseconds: 2_874.9,
            processedFPS: 27,
            p95LatencyMilliseconds: 66.7,
            appDropRate: 0,
            thermalCriticalSeconds: 0,
            thermalSeriousSeconds: 0,
            peakFootprintMB: 750,
            finitePoseRatio: 0.995,
            referenceFirstUsablePoseLatencyMilliseconds: 2_874.9
        )
        XCTAssertTrue(verdict.passed)
    }

    func testLiveReportsEveryFailedGate() {
        let verdict = BenchGateEvaluator.live(
            firstUsablePoseLatencyMilliseconds: 2_875,
            processedFPS: 26,
            p95LatencyMilliseconds: 70,
            appDropRate: 0.02,
            thermalCriticalSeconds: 1,
            thermalSeriousSeconds: 2,
            peakFootprintMB: 800,
            finitePoseRatio: 0.9,
            referenceFirstUsablePoseLatencyMilliseconds: 2_874.9
        )
        XCTAssertFalse(verdict.passed)
        XCTAssertEqual(verdict.failedReasons.count, 8)
        XCTAssertTrue(
            verdict.failedReasons.contains("first_usable_pose_latency_ms>arkit_reference(2874.9)")
        )
    }

    func testColdStartGateIsSkippedWithoutAnArkitReference() {
        let verdict = BenchGateEvaluator.live(
            firstUsablePoseLatencyMilliseconds: 9_999,
            processedFPS: 60,
            p95LatencyMilliseconds: 10,
            appDropRate: 0,
            thermalCriticalSeconds: 0,
            thermalSeriousSeconds: 0,
            peakFootprintMB: 100,
            finitePoseRatio: 1
        )
        XCTAssertTrue(verdict.passed)
    }

    func testLiveGatesAreRelativeToTheArkitReferenceWhenPresent() {
        let ref = LiveReference(processedFPS: 20, p95LatencyMilliseconds: 800, appDropRate: 0.05,
                                thermalCriticalSeconds: 0, thermalSeriousSeconds: 500, peakFootprintMB: 300, finitePoseRatio: 0.9)
        let pass = BenchGateEvaluator.live(
            firstUsablePoseLatencyMilliseconds: 3_000, processedFPS: 26, p95LatencyMilliseconds: 787, appDropRate: 0.01,
            thermalCriticalSeconds: 0, thermalSeriousSeconds: 480, peakFootprintMB: 235, finitePoseRatio: 1,
            referenceFirstUsablePoseLatencyMilliseconds: 3_000, reference: ref)
        XCTAssertTrue(pass.passed, "\(pass.failedReasons)")
        let fail = BenchGateEvaluator.live(
            firstUsablePoseLatencyMilliseconds: 3_000, processedFPS: 10, p95LatencyMilliseconds: 1_600, appDropRate: 0.01,
            thermalCriticalSeconds: 0, thermalSeriousSeconds: 548, peakFootprintMB: 245, finitePoseRatio: 1,
            referenceFirstUsablePoseLatencyMilliseconds: 3_000, reference: ref)
        XCTAssertFalse(fail.passed)
        XCTAssertTrue(fail.failedReasons.contains("processed_fps<arkit_reference(20.0)"))
        XCTAssertTrue(fail.failedReasons.contains("thermal_serious_seconds>arkit_reference(500.0)"))
    }
}
