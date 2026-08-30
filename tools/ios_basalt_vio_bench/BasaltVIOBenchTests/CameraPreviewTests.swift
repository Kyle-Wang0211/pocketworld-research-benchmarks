import ARKit
import XCTest
@testable import VIOReplacementBench

final class CameraPreviewTests: XCTestCase {

    /// Every preview source must draw frames the run already produced. A future
    /// case that opened its own capture session would break the input contract
    /// and, on the ARKit arm, would simply be refused by iOS.
    func testEveryPreviewSourceIsDisplayOnly() {
        let sources: [BenchPreviewSource] = [
            .none, .replayedFrame, .arSession(ARSession()),
        ]
        for source in sources {
            XCTAssertTrue(source.isDisplayOnly, "\(source.receiptMode) is not display-only")
        }
    }

    /// The receipt records how the preview was drawn, so a later reader can tell
    /// whether a run used the shared session or a passthrough.
    func testReceiptModesAreDistinctAndStable() {
        XCTAssertEqual(BenchPreviewSource.none.receiptMode, "none")
        XCTAssertEqual(BenchPreviewSource.replayedFrame.receiptMode, "replayed_frame_passthrough")
        XCTAssertEqual(
            BenchPreviewSource.arSession(ARSession()).receiptMode,
            "arsession_camera_background"
        )
    }

    /// Identity, not equality: two ARKit arms are the same preview only when
    /// they are the same session object.
    func testARSessionSourcesCompareByIdentity() {
        let a = ARSession()
        let b = ARSession()
        XCTAssertEqual(BenchPreviewSource.arSession(a), .arSession(a))
        XCTAssertNotEqual(BenchPreviewSource.arSession(a), .arSession(b))
        XCTAssertNotEqual(BenchPreviewSource.arSession(a), .none)
    }

    /// The preview is framed at the scoring aspect ratio so the operator composes
    /// the capture the way the algorithm receives it.
    func testPreviewAspectMatchesScoringResolution() {
        XCTAssertEqual(
            Double(BenchResolution.scoring.width) / Double(BenchResolution.scoring.height),
            4.0 / 3.0,
            accuracy: 1e-9
        )
    }
}
