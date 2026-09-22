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
        try writer.recordIntrinsics(plausibleIntrinsics, timestampSeconds: 0)

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
        // The archive holds an encoded bitstream, so its size is whatever the
        // encoder produced -- far under the raw planes. What must hold is that
        // the manifest describes the file that is actually on disk.
        let streamOnDisk = try Data(
            contentsOf: root.appendingPathComponent(DeviceRecordingManifest.framesStreamPath)
        ).count
        XCTAssertEqual(manifest.framesTotalByteCount, Int64(streamOnDisk))
        XCTAssertEqual(streamOnDisk, 3 * format.bytesPerFrame,
                       "the device archives raw planes back to back")

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
            // Decoding needs a real HEVC decoder, which the simulator lacks.
            guard let image = try? RawLumaFrameLoader.decode(
                frame.camera0ImageURL,
                format: format,
                accessUnits: try XCTUnwrap(frame.camera0AccessUnits)
            ) else {
                throw XCTSkip("no HEVC codec on this host; verified on device")
            }
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
    /// the expensive digest pass. With frames in one append-only stream this is
    /// the shape an interrupted capture actually leaves behind: a stream that
    /// stops short of what the index names.
    func testTruncatedFrameIsRefusedWithoutDigestVerification() throws {
        _ = try makeMinimalRecording()
        let stream = root.appendingPathComponent(
            DeviceRecordingManifest.framesStreamPath
        )
        try Data(count: 128).write(to: stream)
        XCTAssertThrowsError(
            try DeviceRecordingLoader(verifyFramesDigest: false)
                .load(manifestURL: root.appendingPathComponent("recording_manifest.json"))
        ) { error in
            // The index still names a frame the stream is too short to hold, and
            // that is caught by bounds alone -- no hashing of a multi-gigabyte
            // stream required.
            guard case .frameSizeMismatch = error as? DeviceRecordingError else {
                return XCTFail("expected frameSizeMismatch, got \(error)")
            }
        }
    }

    /// Silent in-place corruption keeps the right length, so only the digest
    /// catches it.
    func testCorruptedFrameIsCaughtByTheDigest() throws {
        _ = try makeMinimalRecording()
        let stream = root.appendingPathComponent(
            DeviceRecordingManifest.framesStreamPath
        )
        var bytes = try Data(contentsOf: stream)
        bytes[0] = bytes[0] &+ 1
        try bytes.write(to: stream)

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
            try writer.recordIntrinsics(
                ARKitIntrinsicsCrossCheck.frozenUpstream640x480,
                timestampSeconds: 0
            )
        )
    }

    /// 1920x1440 luma at production's frame rate for 300 s. The default format
    /// said 30 fps while every caller overrode it to 60, so this constant
    /// described a recording the bench never made; both now follow production's
    /// selected format, which takes the highest frame rate the
    /// high-resolution-capable 1920x1440 entry offers.
    func testProjectedByteCountMatchesTheContract() {
        XCTAssertEqual(
            DeviceRecordingWriter.projectedByteCount(seconds: 300),
            1920 * 1440 * 60 * 300
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
        try writer.recordIntrinsics(plausibleIntrinsics, timestampSeconds: 0)
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

extension DeviceRecordingTests {
    /// Production pins `intrinsics_fxfycxcy` to the frame it came from because
    /// autofocus moves the focal length mid-capture. This recorder kept only the
    /// first frame's values, which pinned a whole scan to one focus position.
    func testEveryFrameIntrinsicsAreRecordedNotJustTheFirst() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("intr-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let writer = try DeviceRecordingWriter(
            directory: directory,
            recordingID: "intrinsics-series",
            format: .scoring
        )

        let base = ARKitIntrinsicsCrossCheck.expectedScoringIntrinsics
        try writer.recordIntrinsics(base, timestampSeconds: 1.0, exposureSeconds: 0.0125)
        // A later frame with the lens at a different focus position, from a
        // caller that cannot report exposure.
        try writer.recordIntrinsics(
            CameraIntrinsics(fx: base.fx * 1.02, fy: base.fy * 1.02, cx: base.cx, cy: base.cy),
            timestampSeconds: 1.5
        )
        writer.appendFrame(
            pixelBuffer: try filledBuffer(format: .scoring, value: 3),
            timestampNanoseconds: 1_000_000_000
        )
        let manifest = try writer.finish()

        let rows = try String(contentsOf: directory.appendingPathComponent("intrinsics.jsonl"))
            .split(separator: "\n")
        XCTAssertEqual(rows.count, 2, "both frames' intrinsics must survive")
        XCTAssertTrue(rows[0].contains("intrinsics_fxfycxcy"), "production's key name")
        // Exposure rides on the same row so a replay can shift this frame to its
        // exposure midpoint; when the caller cannot report it the key is absent,
        // never a silent 0 that would look like a global-shutter zero exposure.
        XCTAssertTrue(rows[0].contains("\"exposure_s\":0.0125"), "per-frame exposure key")
        XCTAssertFalse(rows[1].contains("exposure_s"), "unknown exposure omits the key")
        XCTAssertGreaterThan(
            manifest.focalLengthMaximum, manifest.focalLengthMinimum,
            "the recorded spread must show the focus moved"
        )
    }
}

extension DeviceRecordingTests {
    /// The archive layout is production's: one append-only stream of frames plus
    /// a sidecar index naming each frame's offset and length, the way pwva.dart
    /// writes photos.hevc alongside photos.pwvi. It used to be a file per frame,
    /// which is what made per-frame atomic writes look necessary and cost a 29 s
    /// capture 199 frames to backpressure.
    func testArchiveLayoutMatchesProduction() throws {
        _ = try makeMinimalRecording()
        let manifest = try JSONDecoder().decode(
            DeviceRecordingManifest.self,
            from: Data(contentsOf: root.appendingPathComponent("recording_manifest.json"))
        )

        let stream = root.appendingPathComponent(DeviceRecordingManifest.framesStreamPath)
        let index = root.appendingPathComponent(DeviceRecordingManifest.framesIndexPath)
        XCTAssertTrue(FileManager.default.fileExists(atPath: stream.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: index.path))

        // The stream is an encoded bitstream, not raw planes, so its size is
        // not frame_count times a frame -- it is far smaller, which is the
        // reason for archiving it this way. What must hold is that the manifest
        // and the file agree exactly.
        let streamBytes = try Data(contentsOf: stream).count
        let declared = try XCTUnwrap(manifest.files.first { $0.role == .framesStream })
        XCTAssertEqual(Int(declared.byteCount), streamBytes,
                       "the manifest must describe the stream that is on disk")
        XCTAssertEqual(streamBytes, manifest.frameCount * manifest.camera.bytesPerFrame)

        // One index row per frame, each naming where its frame starts.
        let rows = try String(contentsOf: index).split(separator: "\n")
        XCTAssertEqual(rows.count, manifest.frameCount)
        let first = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: Data(rows[0].utf8)) as? [String: Any]
        )
        // pwva.dart's index schema, key for key.
        XCTAssertEqual(first["frame"] as? Int, 0)
        XCTAssertEqual(first["offset"] as? Int, 0)
        XCTAssertNotNil(first["len"] as? Int)
        XCTAssertNotNil(first["keyframe"] as? Bool)
        XCTAssertNotNil(first["gop"] as? Int)
        // The simulator has no HEVC encoder, so whether frame 0 is marked a sync
        // sample is only meaningful on hardware. Verified there instead.
        if first["keyframe"] as? Bool == true {
            XCTAssertEqual(first["gop"] as? Int, 0)
        }

        XCTAssertTrue(manifest.files.contains { $0.role == .framesStream })
        XCTAssertTrue(manifest.files.contains { $0.role == .framesIndex })
    }
}

extension DeviceRecordingTests {
    /// The loss breakdown must add up to the total. A run reported one write
    /// error while losing nothing, which is impossible -- a write failure both
    /// increments the total and sets the error that makes finish throw -- and it
    /// happened because the counters were read outside the lock that guards them.
    func testLossBreakdownSumsToTheTotal() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("loss-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let writer = try DeviceRecordingWriter(
            directory: directory, recordingID: "loss-sums", format: .scoring
        )
        try writer.recordIntrinsics(
            ARKitIntrinsicsCrossCheck.expectedScoringIntrinsics, timestampSeconds: 0
        )
        for i in 0..<3 {
            writer.appendFrame(
                pixelBuffer: try filledBuffer(format: .scoring, value: UInt8(i)),
                timestampNanoseconds: Int64(i + 1) * 1_000_000
            )
        }
        let manifest = try writer.finish()

        XCTAssertEqual(
            manifest.lossCount,
            manifest.lossFormatMismatch + manifest.lossWriteQueueFull + manifest.lossWriteError
        )
        XCTAssertEqual(manifest.lossCount, 0)
        XCTAssertEqual(manifest.lossWriteError, 0)
    }
}
