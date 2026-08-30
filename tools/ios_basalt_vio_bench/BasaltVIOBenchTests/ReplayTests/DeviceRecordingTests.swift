import CoreVideo
import XCTest
@testable import VIOReplacementBench

final class DeviceRecordingTests: XCTestCase {

    private var root: URL!

    override func setUpWithError() throws {
        root = FileManager.default.temporaryDirectory
            .appendingPathComponent("rec-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
    }

    // MARK: - The stride trap

    /// `CVPixelBuffer` rows are commonly padded past the visible width. Blitting
    /// the plane wholesale would bake the stride into the file and every
    /// replayed frame would be sheared, which looks like an algorithm failure
    /// rather than a recorder failure.
    func testPaddedRowsAreCopiedWithoutShearing() throws {
        let format = DeviceRecordingCameraFormat(
            width: 4, height: 3, pixelFormat: "luma8", nominalFPS: 30
        )
        // Ask for a width whose natural alignment forces padding.
        var buffer: CVPixelBuffer?
        let attributes: [String: Any] = [
            kCVPixelBufferBytesPerRowAlignmentKey as String: 16
        ]
        CVPixelBufferCreate(
            kCFAllocatorDefault, 4, 3,
            kCVPixelFormatType_420YpCbCr8BiPlanarFullRange,
            attributes as CFDictionary, &buffer
        )
        let pixelBuffer = try XCTUnwrap(buffer)

        CVPixelBufferLockBaseAddress(pixelBuffer, [])
        let stride = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0)
        let base = try XCTUnwrap(CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0))
            .assumingMemoryBound(to: UInt8.self)
        // Fill the padding with a sentinel that must not survive the copy.
        for row in 0..<3 {
            for column in 0..<stride {
                base[row * stride + column] = column < 4
                    ? UInt8(row * 4 + column)
                    : 0xFF
            }
        }
        CVPixelBufferUnlockBaseAddress(pixelBuffer, [])

        let copied = try XCTUnwrap(
            DeviceRecordingWriter.copyLumaPlane(pixelBuffer, expected: format)
        )
        XCTAssertEqual(copied.count, 12)
        XCTAssertEqual(Array(copied), Array(0..<12).map(UInt8.init))
        XCTAssertFalse(copied.contains(0xFF), "row padding leaked into the recording")
    }

    func testWrongResolutionBufferIsNotCopied() throws {
        var buffer: CVPixelBuffer?
        CVPixelBufferCreate(
            kCFAllocatorDefault, 8, 8,
            kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, nil, &buffer
        )
        XCTAssertNil(
            DeviceRecordingWriter.copyLumaPlane(
                try XCTUnwrap(buffer),
                expected: DeviceRecordingCameraFormat(
                    width: 4, height: 4, pixelFormat: "luma8", nominalFPS: 30
                )
            )
        )
    }

    // MARK: - Round trip

    /// Writes a recording and replays it, at the real scoring resolution, with
    /// the frames digest verified. This is the property the whole channel rests
    /// on: what the candidates replay is byte-identical to what was captured.
    func testRoundTripPreservesFramesAndOrdering() throws {
        let writer = try DeviceRecordingWriter(directory: root, recordingID: "rt-1")
        try writer.recordIntrinsicsIfNeeded(plausibleIntrinsics)

        let format = DeviceRecordingCameraFormat.scoring
        var expectedFirstByte: [UInt8] = []
        for index in 0..<3 {
            let value = UInt8(index + 1)
            expectedFirstByte.append(value)
            writer.appendFrame(
                pixelBuffer: try filledBuffer(format: format, value: value),
                timestampNanoseconds: Int64(index) * 33_333_333
            )
        }
        for index in 0..<6 {
            writer.appendIMU(
                timestampNanoseconds: Int64(index) * 10_000_000,
                gyroscope: (0.01, 0.02, 0.03),
                acceleration: (0.0, 0.0, -9.80665)
            )
        }
        writer.appendARKitPose(
            timestampNanoseconds: 0,
            tumRow: "0.000000000 0 0 0 0 0 0 1"
        )
        let manifest = try writer.finish()

        XCTAssertEqual(manifest.frameCount, 3)
        XCTAssertEqual(manifest.imuSampleCount, 6)
        XCTAssertEqual(manifest.lossCount, 0, "no loss expected in a 3-frame write")
        XCTAssertEqual(
            manifest.framesTotalByteCount,
            Int64(3 * format.bytesPerFrame)
        )

        let dataset = try DeviceRecordingLoader(verifyFramesDigest: true)
            .load(manifestURL: root.appendingPathComponent("recording_manifest.json"))

        XCTAssertEqual(dataset.recordingID, "rt-1")
        XCTAssertEqual(dataset.inputCameraCount, 1)
        XCTAssertEqual(dataset.events.count, 9)

        // Monotonic, and IMU wins a tie so motion is integrated up to the shutter
        // before the image arrives -- the same ordering EuRoC replay uses.
        var previous: Int64 = .min
        for event in dataset.events {
            XCTAssertGreaterThanOrEqual(event.timestampNanoseconds, previous)
            previous = event.timestampNanoseconds
        }
        XCTAssertEqual(dataset.events.first?.kind, .imu)

        // And the pixels survived.
        let cameras = dataset.events.compactMap { event -> EuRoCCameraFrame? in
            if case .camera(let frame) = event { return frame }
            return nil
        }
        XCTAssertEqual(cameras.count, 3)
        for (index, frame) in cameras.enumerated() {
            let image = try RawLumaFrameLoader.load(frame.camera0ImageURL, format: format)
            XCTAssertEqual(image.width, 1920)
            XCTAssertEqual(image.height, 1440)
            XCTAssertEqual(image.pixels.count, format.bytesPerFrame)
            XCTAssertEqual(image.pixels.first, expectedFirstByte[index])
        }
    }

    /// The recorded stream must drive the shared scheduler unchanged; a second
    /// pacing implementation would be free to drift from the EuRoC one.
    func testRecordedEventsDriveTheSharedScheduler() throws {
        let dataset = try makeMinimalRecording()
        var delivered: [ReplayEvent.Kind] = []
        try ReplayScheduler(mode: .maximumThroughput).run(events: dataset.events) {
            delivered.append($0.kind)
        }
        XCTAssertEqual(delivered.count, dataset.events.count)
    }

    // MARK: - Refusals

    /// A recording with losses is not a shorter recording. Accepting it would
    /// score the candidates on frames ARKit never saw at the times claimed.
    func testLossyRecordingIsRefused() throws {
        try mutateManifest { $0["loss_count"] = 1 }
        XCTAssertThrowsError(try loadRecording()) { error in
            XCTAssertEqual(error as? DeviceRecordingError, .lossyRecording(lossCount: 1))
        }
    }

    func testNonScoringResolutionIsRefused() throws {
        try mutateManifest {
            var camera = $0["camera"] as! [String: Any]
            camera["width"] = 640
            camera["height"] = 480
            $0["camera"] = camera
        }
        XCTAssertThrowsError(try loadRecording()) { error in
            XCTAssertEqual(
                error as? DeviceRecordingError,
                .resolutionIsNotScoring(width: 640, height: 480)
            )
        }
    }

    func testFailedIntrinsicsCrossCheckIsRefused() throws {
        try mutateManifest {
            var intrinsics = $0["intrinsics"] as! [String: Any]
            intrinsics["cross_check_passed"] = false
            $0["intrinsics"] = intrinsics
        }
        XCTAssertThrowsError(try loadRecording()) { error in
            XCTAssertEqual(error as? DeviceRecordingError, .intrinsicsCrossCheckFailed)
        }
    }

    /// Truncation is caught by the always-on structural check, without needing
    /// the expensive digest pass.
    func testTruncatedFrameIsRefusedWithoutDigestVerification() throws {
        _ = try makeMinimalRecording()
        let frame = root.appendingPathComponent(
            DeviceRecordingManifest.frameRelativePath(index: 0)
        )
        try Data(count: 128).write(to: frame)
        XCTAssertThrowsError(
            try DeviceRecordingLoader(verifyFramesDigest: false)
                .load(manifestURL: root.appendingPathComponent("recording_manifest.json"))
        ) { error in
            guard case .frameSizeMismatch = error as? DeviceRecordingError else {
                return XCTFail("expected frameSizeMismatch, got \(error)")
            }
        }
    }

    /// Silent in-place corruption keeps the right length, so only the digest
    /// catches it.
    func testCorruptedFrameIsCaughtByTheDigest() throws {
        _ = try makeMinimalRecording()
        let frame = root.appendingPathComponent(
            DeviceRecordingManifest.frameRelativePath(index: 0)
        )
        var bytes = try Data(contentsOf: frame)
        bytes[0] = bytes[0] &+ 1
        try bytes.write(to: frame)

        XCTAssertNoThrow(
            try DeviceRecordingLoader(verifyFramesDigest: false)
                .load(manifestURL: root.appendingPathComponent("recording_manifest.json")),
            "same length, so the structural check cannot see this"
        )
        XCTAssertThrowsError(
            try DeviceRecordingLoader(verifyFramesDigest: true)
                .load(manifestURL: root.appendingPathComponent("recording_manifest.json"))
        ) { error in
            guard case .framesDigestMismatch = error as? DeviceRecordingError else {
                return XCTFail("expected framesDigestMismatch, got \(error)")
            }
        }
    }

    func testIntrinsicsThatFailCrossCheckAreRejectedAtRecordTime() throws {
        let writer = try DeviceRecordingWriter(directory: root, recordingID: "bad")
        XCTAssertThrowsError(
            // The unscaled 640x480 values: the exact mistake the check exists for.
            try writer.recordIntrinsicsIfNeeded(
                ARKitIntrinsicsCrossCheck.frozenUpstream640x480
            )
        )
    }

    func testProjectedByteCountMatchesTheContract() {
        XCTAssertEqual(
            DeviceRecordingWriter.projectedByteCount(seconds: 300),
            24_883_200_000
        )
    }

    // MARK: - Helpers

    private var plausibleIntrinsics: CameraIntrinsics {
        CameraIntrinsics(fx: 1346.9, fy: 1347.4, cx: 964.0, cy: 722.1)
    }

    private func filledBuffer(
        format: DeviceRecordingCameraFormat,
        value: UInt8
    ) throws -> CVPixelBuffer {
        var buffer: CVPixelBuffer?
        CVPixelBufferCreate(
            kCFAllocatorDefault, format.width, format.height,
            kCVPixelFormatType_420YpCbCr8BiPlanarFullRange, nil, &buffer
        )
        let pixelBuffer = try XCTUnwrap(buffer)
        CVPixelBufferLockBaseAddress(pixelBuffer, [])
        let stride = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0)
        let base = try XCTUnwrap(CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0))
            .assumingMemoryBound(to: UInt8.self)
        memset(base, Int32(value), stride * format.height)
        CVPixelBufferUnlockBaseAddress(pixelBuffer, [])
        return pixelBuffer
    }

    @discardableResult
    private func makeMinimalRecording() throws -> DeviceRecordingDataset {
        let writer = try DeviceRecordingWriter(directory: root, recordingID: "min")
        try writer.recordIntrinsicsIfNeeded(plausibleIntrinsics)
        writer.appendFrame(
            pixelBuffer: try filledBuffer(format: .scoring, value: 7),
            timestampNanoseconds: 0
        )
        writer.appendIMU(
            timestampNanoseconds: 0,
            gyroscope: (0, 0, 0),
            acceleration: (0, 0, -9.80665)
        )
        writer.appendARKitPose(
            timestampNanoseconds: 0,
            tumRow: "0.000000000 0 0 0 0 0 0 1"
        )
        try writer.finish()
        return try loadRecording()
    }

    private func loadRecording() throws -> DeviceRecordingDataset {
        try DeviceRecordingLoader(verifyFramesDigest: false)
            .load(manifestURL: root.appendingPathComponent("recording_manifest.json"))
    }

    private func mutateManifest(_ edit: (inout [String: Any]) -> Void) throws {
        _ = try? makeMinimalRecording()
        let url = root.appendingPathComponent("recording_manifest.json")
        var json = try JSONSerialization.jsonObject(
            with: Data(contentsOf: url)
        ) as! [String: Any]
        edit(&json)
        try JSONSerialization.data(withJSONObject: json, options: [.sortedKeys])
            .write(to: url, options: .atomic)
    }
}
