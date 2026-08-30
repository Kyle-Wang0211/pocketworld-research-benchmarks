import XCTest
@testable import VIOReplacementBench

final class BenchResolutionTests: XCTestCase {

    /// Production's shipped configuration: pwVideoFormat = "hires43", the
    /// high-resolution-capable 1920x1440 4:3 entry. Intrinsics are the values
    /// this device reported during the operator's own 30 s capture.
    private static let productionWidth = 1920
    private static let productionHeight = 1440
    private static let productionIntrinsics = CameraIntrinsics(
        fx: 1341.84, fy: 1341.84, cx: 957.50, cy: 718.91
    )

    func testScoringResolutionIsProductionsOwn() {
        XCTAssertEqual(BenchResolution.scoring.width, Self.productionWidth)
        XCTAssertEqual(BenchResolution.scoring.height, Self.productionHeight)
        XCTAssertEqual(BenchResolution.scoringFramesPerSecond, 60)
    }

    func testOnlyProductionResolutionParticipatesInVerdicts() {
        XCTAssertTrue(
            BenchResolution.participatesInVerdict(
                width: Self.productionWidth, height: Self.productionHeight
            )
        )
        // Production's documented fallback format, and the diagnostic scale.
        XCTAssertFalse(BenchResolution.participatesInVerdict(width: 3840, height: 2160))
        XCTAssertFalse(BenchResolution.participatesInVerdict(width: 640, height: 480))
    }

    /// The values ARKit reported for production's format must be accepted. They
    /// were refused before, because the gate compared them against xrslam's
    /// 640x480 config scaled by 3 -- a candidate engine's calibration used to
    /// invalidate production's own capture.
    func testProductionIntrinsicsAreAccepted() {
        let verdict = ARKitIntrinsicsCrossCheck.check(
            arkitReported: Self.productionIntrinsics,
            frameWidth: Self.productionWidth,
            frameHeight: Self.productionHeight
        )
        guard case .agrees(let scoring) = verdict else {
            return XCTFail("production's own intrinsics must be accepted, got \(verdict)")
        }
        XCTAssertEqual(scoring, Self.productionIntrinsics)
        XCTAssertFalse(verdict.haltsRun)
    }

    /// A focal length far from any frozen constant is not by itself a fault:
    /// autofocus moves it, and production records it per frame for that reason.
    func testFocalLengthFarFromAnyConstantStillPasses() {
        let drifted = CameraIntrinsics(
            fx: Self.productionIntrinsics.fx * 1.2,
            fy: Self.productionIntrinsics.fy * 1.2,
            cx: Self.productionIntrinsics.cx,
            cy: Self.productionIntrinsics.cy
        )
        XCTAssertFalse(
            ARKitIntrinsicsCrossCheck.check(
                arkitReported: drifted,
                frameWidth: Self.productionWidth,
                frameHeight: Self.productionHeight
            ).haltsRun
        )
    }

    /// What still halts a run: intrinsics that cannot describe the frames they
    /// arrived with. A principal point far off centre means the numbers and the
    /// pixels are about different images.
    func testPrincipalPointFarFromFrameCentreHaltsTheRun() {
        let verdict = ARKitIntrinsicsCrossCheck.check(
            arkitReported: CameraIntrinsics(fx: 1341.84, fy: 1341.84, cx: 400, cy: 718.91),
            frameWidth: Self.productionWidth,
            frameHeight: Self.productionHeight
        )
        XCTAssertTrue(verdict.haltsRun)
        XCTAssertEqual(verdict.reason, "arkit_intrinsics_disagree_cx")
    }

    /// Intrinsics for a 3840x2160 frame against a 1920x1440 recording: the
    /// mismatch that went unnoticed while the bench ran production's fallback
    /// format instead of its shipped one.
    func testIntrinsicsForTheWrongFormatHaltTheRun() {
        let verdict = ARKitIntrinsicsCrossCheck.check(
            arkitReported: CameraIntrinsics(fx: 2609.13, fy: 2609.13, cx: 1924.58, cy: 1081.92),
            frameWidth: Self.productionWidth,
            frameHeight: Self.productionHeight
        )
        XCTAssertTrue(verdict.haltsRun)
    }

    func testNonFiniteIntrinsicsHaltTheRun() {
        for bad in [Double.nan, .infinity] {
            let verdict = ARKitIntrinsicsCrossCheck.check(
                arkitReported: CameraIntrinsics(fx: bad, fy: 1341.84, cx: 957.50, cy: 718.91),
                frameWidth: Self.productionWidth,
                frameHeight: Self.productionHeight
            )
            XCTAssertEqual(verdict.reason, "arkit_intrinsics_non_finite")
        }
    }

    func testNonPositiveFocalLengthHaltsTheRun() {
        XCTAssertTrue(
            ARKitIntrinsicsCrossCheck.check(
                arkitReported: CameraIntrinsics(fx: 0, fy: 1341.84, cx: 957.50, cy: 718.91),
                frameWidth: Self.productionWidth,
                frameHeight: Self.productionHeight
            ).haltsRun
        )
    }
}
