import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers
import XCTest
@testable import VIOReplacementBench

final class GrayscaleImageLoaderTests: XCTestCase {
    func testPNGDecodePreservesExactGrayRowsAndColumns() throws {
        let expected = Data([10, 20, 30, 40, 50, 60])
        let provider = CGDataProvider(data: expected as CFData)!
        let image = CGImage(
            width: 3,
            height: 2,
            bitsPerComponent: 8,
            bitsPerPixel: 8,
            bytesPerRow: 3,
            space: CGColorSpaceCreateDeviceGray(),
            bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
            provider: provider,
            decode: nil,
            shouldInterpolate: false,
            intent: .defaultIntent
        )!
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("gray-\(UUID().uuidString).png")
        defer { try? FileManager.default.removeItem(at: url) }
        let destination = CGImageDestinationCreateWithURL(
            url as CFURL,
            UTType.png.identifier as CFString,
            1,
            nil
        )!
        CGImageDestinationAddImage(destination, image, nil)
        XCTAssertTrue(CGImageDestinationFinalize(destination))

        let decoded = try GrayscaleImageLoader.load(
            url,
            expectedWidth: 3,
            expectedHeight: 2
        )
        XCTAssertEqual(decoded.bytesPerRow, 3)
        XCTAssertEqual(decoded.pixels, expected)
    }
}
