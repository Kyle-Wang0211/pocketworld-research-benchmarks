import CoreVideo
import XCTest
@testable import VIOReplacementBench

final class LiveCaptureFormatReceiptTests: XCTestCase {
    func testFourCCPreservesPinnedFullRangeIdentity() {
        XCTAssertEqual(
            LiveCaptureFormatReceipt.fourCC(
                kCVPixelFormatType_420YpCbCr8BiPlanarFullRange
            ),
            "420f"
        )
    }
}
