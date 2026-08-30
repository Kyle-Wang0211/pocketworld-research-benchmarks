import XCTest
@testable import VIOReplacementBench

final class BenchResolutionTests: XCTestCase {

    func testOnly1920x1440ParticipatesInVerdicts() {
        XCTAssertTrue(BenchResolution.participatesInVerdict(width: 1920, height: 1440))
        XCTAssertFalse(BenchResolution.participatesInVerdict(width: 640, height: 480))
    }

    /// The scaled upstream values the contract records as the cross-check target.
    func testExpectedScoringIntrinsicsMatchContract() {
        let e = ARKitIntrinsicsCrossCheck.expectedScoringIntrinsics
        XCTAssertEqual(e.fx, 1346.903, accuracy: 0.001)
        XCTAssertEqual(e.fy, 1347.432, accuracy: 0.001)
        XCTAssertEqual(e.cx, 964.038, accuracy: 0.001)
        XCTAssertEqual(e.cy, 722.149, accuracy: 0.001)
    }

    /// The scaled principal point must land on the 1920x1440 centre. If it does
    /// not, the two formats are not related by a pure scale and the whole
    /// cross-check premise is wrong.
    func testScaledPrincipalPointIsNearFrameCentre() {
        let e = ARKitIntrinsicsCrossCheck.expectedScoringIntrinsics
        XCTAssertEqual(e.cx, Double(BenchResolution.scoring.width) / 2, accuracy: 6)
        XCTAssertEqual(e.cy, Double(BenchResolution.scoring.height) / 2, accuracy: 6)
    }

    func testPlausibleDeviceReadingAgreesAndWins() {
        // A factory per-device calibration a few pixels off the sample device.
        let reported = CameraIntrinsics(fx: 1349.1, fy: 1349.6, cx: 961.4, cy: 719.2)
        let verdict = ARKitIntrinsicsCrossCheck.check(arkitReported: reported)
        guard case .agrees(let scoring) = verdict else {
            return XCTFail("expected agreement, got \(verdict)")
        }
        XCTAssertEqual(scoring, reported, "ARKit's own values must win once they agree")
        XCTAssertFalse(verdict.haltsRun)
    }

    /// A crop rather than a scale moves the principal point far more than
    /// per-device variation ever does, and must halt the run.
    func testCroppedFormatIsRejected() {
        let cropped = CameraIntrinsics(fx: 1346.9, fy: 1347.4, cx: 820.0, cy: 722.1)
        let verdict = ARKitIntrinsicsCrossCheck.check(arkitReported: cropped)
        XCTAssertTrue(verdict.haltsRun)
        XCTAssertEqual(verdict.reason, "arkit_intrinsics_disagree_cx")
    }

    /// Forgetting to scale is the exact mistake this check exists to catch.
    func testUnscaled640x480ValuesAreRejected() {
        let verdict = ARKitIntrinsicsCrossCheck.check(
            arkitReported: ARKitIntrinsicsCrossCheck.frozenUpstream640x480
        )
        XCTAssertTrue(verdict.haltsRun)
        XCTAssertEqual(verdict.reason, "arkit_intrinsics_disagree_fx")
    }

    func testNonFiniteIntrinsicsHaltTheRun() {
        for bad in [Double.nan, .infinity] {
            let verdict = ARKitIntrinsicsCrossCheck.check(
                arkitReported: CameraIntrinsics(fx: bad, fy: 1347.4, cx: 964.0, cy: 722.1)
            )
            XCTAssertEqual(verdict.reason, "arkit_intrinsics_non_finite")
        }
    }

    func testToleranceBoundaryIsInclusive() {
        let e = ARKitIntrinsicsCrossCheck.expectedScoringIntrinsics
        let t = ARKitIntrinsicsCrossCheck.toleranceP
        XCTAssertFalse(
            ARKitIntrinsicsCrossCheck.check(
                arkitReported: CameraIntrinsics(fx: e.fx + t, fy: e.fy, cx: e.cx, cy: e.cy)
            ).haltsRun
        )
        XCTAssertTrue(
            ARKitIntrinsicsCrossCheck.check(
                arkitReported: CameraIntrinsics(fx: e.fx + t + 0.001, fy: e.fy, cx: e.cx, cy: e.cy)
            ).haltsRun
        )
    }
}
