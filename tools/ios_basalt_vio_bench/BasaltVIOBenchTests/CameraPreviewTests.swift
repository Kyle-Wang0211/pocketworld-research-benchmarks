import CoreVideo
import XCTest
@testable import VIOReplacementBench

final class CameraPreviewTests: XCTestCase {

    /// Every preview source must draw frames the run already produced. The
    /// rejected alternative was handing the ARSession to an ARSCNView, which
    /// takes the session's delegate and would have silently stopped
    /// ARKitReferenceSession.didUpdate -- killing accounting and recording while
    /// the screen looked healthy.
    func testEveryPreviewSourceIsDisplayOnly() {
        for source: BenchPreviewSource in [.none, .liveFrames(label: "Basalt")] {
            XCTAssertTrue(source.isDisplayOnly, "\(source.receiptMode) is not display-only")
        }
    }

    func testReceiptModesAreDistinctAndStable() {
        XCTAssertEqual(BenchPreviewSource.none.receiptMode, "none")
        XCTAssertEqual(
            BenchPreviewSource.liveFrames(label: "ARKit").receiptMode,
            "accepted_frame_passthrough"
        )
    }

    /// Decimation must skip rows using the buffer's stride, not the visible
    /// width. Using width would drift across the padding and shear the preview.
    func testDecimationUsesStrideAndSkipsWithoutInterpolating() throws {
        var buffer: CVPixelBuffer?
        CVPixelBufferCreate(
            kCFAllocatorDefault, 16, 16,
            kCVPixelFormatType_420YpCbCr8BiPlanarFullRange,
            [kCVPixelBufferBytesPerRowAlignmentKey as String: 64] as CFDictionary,
            &buffer
        )
        let pixelBuffer = try XCTUnwrap(buffer)
        CVPixelBufferLockBaseAddress(pixelBuffer, [])
        let stride = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0)
        let base = try XCTUnwrap(CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0))
            .assumingMemoryBound(to: UInt8.self)
        for row in 0..<16 {
            for column in 0..<stride {
                // Visible pixels encode their column; padding is a sentinel.
                base[row * stride + column] = column < 16 ? UInt8(column) : 0xFF
            }
        }
        CVPixelBufferUnlockBaseAddress(pixelBuffer, [])

        let small = try XCTUnwrap(PreviewFrameTap.decimatedLuma(pixelBuffer))
        XCTAssertEqual(small.width, 4)
        XCTAssertEqual(small.height, 4)
        // Nearest neighbour with decimation 4 samples columns 0, 4, 8, 12.
        XCTAssertEqual(Array(small.pixels.prefix(4)), [0, 4, 8, 12])
        XCTAssertFalse(small.pixels.contains(0xFF), "row padding leaked into the preview")
        XCTAssertNotNil(PreviewFrameTap.makeImage(small))
    }

    /// The tap is rate limited so the arm being measured is not measuring the
    /// preview. Frames offered inside the interval must be dropped, not queued.
    func testTapIsRateLimited() throws {
        let published = NSMutableArray()
        let tap = PreviewFrameTap { published.add($0) }
        var buffer: CVPixelBuffer?
        CVPixelBufferCreate(
            kCFAllocatorDefault, 64, 64,
            kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, nil, &buffer
        )
        let pixelBuffer = try XCTUnwrap(buffer)

        tap.offer(pixelBuffer: pixelBuffer, monotonicNanoseconds: 1_000_000_000)
        // 10 ms later: well inside the 100 ms interval, must be ignored.
        tap.offer(pixelBuffer: pixelBuffer, monotonicNanoseconds: 1_010_000_000)
        let deadline = Date().addingTimeInterval(2)
        while published.count < 1 && Date() < deadline { usleep(10_000) }
        XCTAssertEqual(published.count, 1, "second offer was inside the rate limit")
    }

    /// Preview is framed portrait, matching how the phone is held, from a
    /// landscape 1920x1440 sensor.
    func testPreviewAspectMatchesScoringResolution() {
        XCTAssertEqual(
            Double(BenchResolution.scoring.height) / Double(BenchResolution.scoring.width),
            3.0 / 4.0,
            accuracy: 1e-9
        )
    }
}
