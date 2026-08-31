import CryptoKit
import Foundation

/// Reads a raw luma frame back exactly as it was captured.
///
/// `GrayscaleImageLoader` decodes encoded images; recorded frames are not
/// encoded, so there is nothing to decode. The file *is* the plane, and the only
/// check that matters is that its length is exactly one frame -- a short or long
/// file means the recording is not what its manifest says.
enum RawLumaFrameLoader {
    /// Decodes one frame out of the archived bitstream. [accessUnits] runs from
    /// the frame's GOP keyframe to the frame itself, the order production
    /// decodes in; a decoder is built from the keyframe and fed forward.
    static func decode(
        _ url: URL,
        format: DeviceRecordingCameraFormat,
        accessUnits: [Range<Int>]
    ) throws -> GrayscaleImage {
        let stream = try Data(contentsOf: url, options: .mappedIfSafe)
        guard let first = accessUnits.first,
              first.lowerBound >= 0, first.upperBound <= stream.count else {
            throw DeviceRecordingError.missingFrame(url.lastPathComponent)
        }

        // The device archives raw planes: encoding on the phone did not survive
        // either placement, so the bytes are the plane and there is nothing to
        // decode. An entry exactly one frame long is that case; anything shorter
        // is an encoded access unit, which is what an off-device transcode
        // produces.
        if let only = accessUnits.last,
           accessUnits.count == 1,
           only.count == format.bytesPerFrame {
            guard only.upperBound <= stream.count else {
                throw DeviceRecordingError.frameSizeMismatch(
                    path: url.lastPathComponent,
                    expected: format.bytesPerFrame,
                    actual: max(0, stream.count - only.lowerBound)
                )
            }
            return GrayscaleImage(
                width: format.width, height: format.height,
                bytesPerRow: format.width, pixels: stream.subdata(in: only)
            )
        }
        let keyframe = stream.subdata(in: first)
        let decoder: OpaquePointer? = keyframe.withUnsafeBytes { key in
            pw_vt_dec_create(
                Int32(format.width), Int32(format.height),
                key.bindMemory(to: UInt8.self).baseAddress, Int64(keyframe.count)
            )
        }
        guard let decoder else { throw DeviceRecordingError.decoderUnavailable }
        defer { pw_vt_dec_destroy(decoder) }

        var luma = [UInt8](repeating: 0, count: format.bytesPerFrame)
        var chroma = [UInt8](repeating: 0, count: format.bytesPerFrame / 2)
        for range in accessUnits {
            guard range.lowerBound >= 0, range.upperBound <= stream.count else {
                throw DeviceRecordingError.missingFrame(url.lastPathComponent)
            }
            let au = stream.subdata(in: range)
            let status: Int32 = au.withUnsafeBytes { bytes in
                luma.withUnsafeMutableBufferPointer { y in
                    chroma.withUnsafeMutableBufferPointer { uv in
                        pw_vt_dec_decode(
                            decoder,
                            bytes.bindMemory(to: UInt8.self).baseAddress, Int64(au.count),
                            y.baseAddress, uv.baseAddress
                        )
                    }
                }
            }
            guard status == 0 else {
                throw DeviceRecordingError.decodeFailed(status: Int(status))
            }
        }
        return GrayscaleImage(
            width: format.width, height: format.height,
            bytesPerRow: format.width, pixels: Data(luma)
        )
    }

    static func load(
        _ url: URL,
        format: DeviceRecordingCameraFormat
    ) throws -> GrayscaleImage {
        let data = try Data(contentsOf: url, options: .mappedIfSafe)
        guard data.count == format.bytesPerFrame else {
            throw DeviceRecordingError.frameSizeMismatch(
                path: url.lastPathComponent,
                expected: format.bytesPerFrame,
                actual: data.count
            )
        }
        return GrayscaleImage(
            width: format.width,
            height: format.height,
            bytesPerRow: format.width,
            pixels: data
        )
    }
}

/// Loads a device recording into the same `[ReplayEvent]` stream `ReplayScheduler`
/// already drives for EuRoC, so pacing, ordering and delivery are shared code
/// rather than a second implementation that can drift.
struct DeviceRecordingLoader {

    /// Re-streaming 23 GiB to verify the frames digest costs real time, so it is
    /// opt-in: on when freezing a recording or auditing one, off for the many
    /// replays that follow. Structural checks -- every frame present and exactly
    /// one frame long -- always run, because they are cheap and catch truncation.
    let verifyFramesDigest: Bool


    init(verifyFramesDigest: Bool = false) {
        self.verifyFramesDigest = verifyFramesDigest
    }

    func load(manifestURL: URL) throws -> DeviceRecordingDataset {
        let root = manifestURL.deletingLastPathComponent()
        let manifest = try JSONDecoder().decode(
            DeviceRecordingManifest.self,
            from: Data(contentsOf: manifestURL)
        )

        guard manifest.schemaVersion == DeviceRecordingManifest.supportedSchemaVersion else {
            throw DeviceRecordingError.unsupportedSchemaVersion(manifest.schemaVersion)
        }
        guard !manifest.recordingID.isEmpty else {
            throw DeviceRecordingError.invalidRecordingID
        }
        // A recording at any other resolution cannot be scored, so it is refused
        // here rather than silently producing numbers nobody may use.
        guard BenchResolution.participatesInVerdict(
            width: manifest.camera.width,
            height: manifest.camera.height
        ) else {
            throw DeviceRecordingError.resolutionIsNotScoring(
                width: manifest.camera.width,
                height: manifest.camera.height
            )
        }
        guard manifest.lossCount == 0 else {
            throw DeviceRecordingError.lossyRecording(lossCount: manifest.lossCount)
        }
        guard manifest.intrinsics.crossCheckPassed else {
            throw DeviceRecordingError.intrinsicsCrossCheckFailed
        }

        try verifyIndexFiles(manifest.files, root: root)

        let cameraRecord = try required(.cameraIndex, in: manifest.files)
        let imuRecord = try required(.imuIndex, in: manifest.files)
        let poseRecord = try required(.arkitPoses, in: manifest.files)

        let streamRecord = try required(.framesStream, in: manifest.files)
        try rejectUnsafePath(streamRecord.relativePath)
        let streamURL = root.appendingPathComponent(streamRecord.relativePath)
        // The bound has to come from the file on disk, not from the manifest's
        // claim about it: an interrupted capture leaves a stream shorter than
        // the manifest says, and trusting the manifest would let that through.
        let streamAttributes = try? FileManager.default.attributesOfItem(
            atPath: streamURL.path
        )
        guard let streamSize = streamAttributes?[.size] as? Int64 else {
            throw DeviceRecordingError.missingFrame(streamRecord.relativePath)
        }
        let indexRecord = try required(.framesIndex, in: manifest.files)
        try rejectUnsafePath(indexRecord.relativePath)
        let entries = try parseArchiveIndex(
            url: root.appendingPathComponent(indexRecord.relativePath),
            streamByteCount: Int(streamSize)
        )
        let frames = try parseCameraIndex(
            record: cameraRecord,
            root: root,
            format: manifest.camera,
            streamURL: streamURL,
            entries: entries
        )
        guard frames.count == manifest.frameCount else {
            throw DeviceRecordingError.frameCountMismatch(
                declared: manifest.frameCount,
                indexed: frames.count
            )
        }
        let imu = try parseIMU(record: imuRecord, root: root)
        guard !frames.isEmpty || !imu.isEmpty else {
            throw DeviceRecordingError.emptyRecording
        }

        if verifyFramesDigest {
            try verifyDigest(frames: frames, expected: manifest.framesDigestSHA256)
        }

        let arkitReference = try TUMTrajectoryLoader().load(
            url: root.appendingPathComponent(poseRecord.relativePath)
        )

        // IMU first at an equal timestamp: the estimator must have integrated
        // motion up to the shutter before the image arrives, which is the same
        // ordering the EuRoC path uses.
        var events: [ReplayEvent] = imu.map { .imu($0) } + frames.map { .camera($0) }
        events.sort {
            $0.timestampNanoseconds == $1.timestampNanoseconds
                ? $0.kind.rawValue < $1.kind.rawValue
                : $0.timestampNanoseconds < $1.timestampNanoseconds
        }

        // Motion recording starts at the end of the first camera callback, so a
        // capture opens with camera frames that have no inertial data behind
        // them -- 77 ms, about five frames, in the recording this was found on.
        // A visual-inertial system cannot use those frames, and xrslam does not
        // merely ignore them: it takes a SIGBUS inside push_sensor_data on the
        // first one. They are dropped here rather than left for each engine to
        // survive or not.
        if let firstIMU = imu.first?.timestampNanoseconds {
            let before = events.count
            events.removeAll {
                if case .camera(let frame) = $0 {
                    return frame.timestampNanoseconds < firstIMU
                }
                return false
            }
            let dropped = before - events.count
            if dropped > 0 {
                NSLog("[VIOBench] dropped %d leading camera frames with no IMU behind them",
                      dropped)
            }
        }

        return DeviceRecordingDataset(
            recordingID: manifest.recordingID,
            camera: manifest.camera,
            intrinsics: manifest.intrinsics,
            events: events,
            arkitReference: arkitReference
        )
    }

    // MARK: - Verification

    private func verifyIndexFiles(
        _ files: [DeviceRecordingFile],
        root: URL
    ) throws {
        // The frame stream is the bulk payload -- 4.9 GB for a 30 s capture --
        // and hashing it on every load would make opening a recording cost as
        // much as replaying it. Its manifest hash is written at close, the way
        // production writes the stream's SHA-256 into its own manifest, and is
        // checked here only under the same flag as the frames digest.
        let payloadRoles: Set<DeviceRecordingFileRole> = [.framesStream]
        for record in files where !payloadRoles.contains(record.role) {
            try rejectUnsafePath(record.relativePath)
            let url = root.appendingPathComponent(record.relativePath)
            let data = try Data(contentsOf: url)
            let actual = DeviceRecordingWriter.hex(SHA256.hash(data: data))
            guard actual == record.sha256 else {
                throw DeviceRecordingError.fileHashMismatch(
                    path: record.relativePath,
                    expected: record.sha256,
                    actual: actual
                )
            }
        }
    }

    private func verifyDigest(
        frames: [EuRoCCameraFrame],
        expected: String
    ) throws {
        var digest = SHA256()
        // The digest covers frame payloads in capture order, which is what the
        // writer hashed. Reading the stream once and slicing it keeps that true
        // without reopening it per frame.
        var streamCache: [URL: Data] = [:]
        for frame in frames {
            let whole: Data
            if let cached = streamCache[frame.camera0ImageURL] {
                whole = cached
            } else {
                whole = try Data(contentsOf: frame.camera0ImageURL, options: .mappedIfSafe)
                streamCache[frame.camera0ImageURL] = whole
            }
            // The writer hashed the stream as it wrote it, so the digest is
            // over each frame's own access unit in capture order -- the last
            // range of each frame's decode list.
            if let last = frame.camera0AccessUnits?.last {
                digest.update(data: whole.subdata(in: last))
            } else {
                digest.update(data: whole)
            }
        }
        let actual = DeviceRecordingWriter.hex(digest.finalize())
        guard actual == expected else {
            throw DeviceRecordingError.framesDigestMismatch(expected: expected, actual: actual)
        }
    }

    private func required(
        _ role: DeviceRecordingFileRole,
        in files: [DeviceRecordingFile]
    ) throws -> DeviceRecordingFile {
        guard let record = files.first(where: { $0.role == role }) else {
            throw DeviceRecordingError.missingRequiredRole(role)
        }
        return record
    }

    private func rejectUnsafePath(_ path: String) throws {
        guard !path.isEmpty,
              !path.hasPrefix("/"),
              !path.contains(".."),
              !path.contains("\\") else {
            throw DeviceRecordingError.unsafeRelativePath(path)
        }
    }

    // MARK: - Parsing

    /// One row of production's index schema: frame, offset, len, keyframe, gop.
    private struct ArchiveIndexEntry {
        let frame: Int
        let offset: Int
        let len: Int
        let keyframe: Bool
    }

    private func parseArchiveIndex(
        url: URL,
        streamByteCount: Int
    ) throws -> [ArchiveIndexEntry] {
        var entries: [ArchiveIndexEntry] = []
        let text = try String(contentsOf: url, encoding: .utf8)
        for (line, raw) in text.split(separator: "\n").enumerated() {
            guard let object = try JSONSerialization.jsonObject(
                with: Data(raw.utf8)
            ) as? [String: Any],
                let frame = object["frame"] as? Int,
                let offset = object["offset"] as? Int,
                let len = object["len"] as? Int,
                let keyframe = object["keyframe"] as? Bool else {
                throw DeviceRecordingError.malformedCSV(
                    path: url.lastPathComponent, line: line + 1, reason: "index_row"
                )
            }
            // An interrupted capture leaves the stream short of what a later
            // index row names; bounds come from the file, never the manifest.
            guard offset >= 0, len > 0, offset + len <= streamByteCount else {
                throw DeviceRecordingError.frameSizeMismatch(
                    path: url.lastPathComponent,
                    expected: len,
                    actual: max(0, streamByteCount - offset)
                )
            }
            entries.append(
                ArchiveIndexEntry(frame: frame, offset: offset, len: len, keyframe: keyframe)
            )
        }
        return entries
    }

    private func parseCameraIndex(
        record: DeviceRecordingFile,
        root: URL,
        format: DeviceRecordingCameraFormat,
        streamURL: URL,
        entries: [ArchiveIndexEntry]
    ) throws -> [EuRoCCameraFrame] {
        var frames: [EuRoCCameraFrame] = []
        var previous: Int64?
        try forEachRow(record: record, root: root, expectedColumns: 2) { line, fields in
            guard let timestamp = Int64(fields[0]) else {
                throw DeviceRecordingError.malformedCSV(
                    path: record.relativePath, line: line, reason: "timestamp_ns"
                )
            }
            if let previous, timestamp <= previous {
                throw DeviceRecordingError.timestampRegression(
                    path: record.relativePath, previous: previous, current: timestamp
                )
            }
            previous = timestamp
            guard let frameIndex = Int(fields[1]), frameIndex >= 0 else {
                throw DeviceRecordingError.malformedCSV(
                    path: record.relativePath, line: line, reason: "frame_index"
                )
            }
            // Frames live back to back in one stream, so a frame is an offset
            // and a length. The structural check is the same one the per-file
            // layout got -- present, and exactly one frame long -- but it is now
            // a bounds check against the stream, which is what catches a capture
            // truncated by an interrupt before it becomes a measurement.
            guard frameIndex < entries.count else {
                throw DeviceRecordingError.frameCountMismatch(
                    declared: frameIndex + 1, indexed: entries.count
                )
            }
            // Decoding starts at the GOP keyframe and runs forward to this
            // frame, which is how production reads its archive back.
            var start = frameIndex
            while start > 0 && !entries[start].keyframe { start -= 1 }
            let units = (start...frameIndex).map {
                entries[$0].offset ..< (entries[$0].offset + entries[$0].len)
            }
            frames.append(EuRoCCameraFrame(
                timestampNanoseconds: timestamp,
                camera0ImageURL: streamURL,
                camera1ImageURL: nil,
                camera0AccessUnits: units
            ))
        }
        return frames
    }

    private func parseIMU(
        record: DeviceRecordingFile,
        root: URL
    ) throws -> [EuRoCIMUSample] {
        var samples: [EuRoCIMUSample] = []
        var previous: Int64?
        try forEachRow(record: record, root: root, expectedColumns: 7) { line, fields in
            guard let timestamp = Int64(fields[0]) else {
                throw DeviceRecordingError.malformedCSV(
                    path: record.relativePath, line: line, reason: "timestamp_ns"
                )
            }
            if let previous, timestamp <= previous {
                throw DeviceRecordingError.timestampRegression(
                    path: record.relativePath, previous: previous, current: timestamp
                )
            }
            previous = timestamp
            let values = try fields.dropFirst().map { field -> Double in
                guard let value = Double(field), value.isFinite else {
                    throw DeviceRecordingError.malformedCSV(
                        path: record.relativePath, line: line, reason: "non-finite \(field)"
                    )
                }
                return value
            }
            samples.append(EuRoCIMUSample(
                timestampNanoseconds: timestamp,
                gyroscopeRadiansPerSecond: Vector3(x: values[0], y: values[1], z: values[2]),
                accelerationMetersPerSecondSquared: Vector3(x: values[3], y: values[4], z: values[5])
            ))
        }
        return samples
    }

    private func forEachRow(
        record: DeviceRecordingFile,
        root: URL,
        expectedColumns: Int,
        body: (Int, [String]) throws -> Void
    ) throws {
        let text = try String(
            contentsOf: root.appendingPathComponent(record.relativePath),
            encoding: .utf8
        )
        for (offset, rawLine) in text.split(separator: "\n", omittingEmptySubsequences: false).enumerated() {
            let line = rawLine.trimmingCharacters(in: .whitespaces)
            if line.isEmpty || offset == 0 { continue }  // row 0 is the header
            let fields = line.split(separator: ",", omittingEmptySubsequences: false).map(String.init)
            guard fields.count == expectedColumns else {
                throw DeviceRecordingError.malformedCSV(
                    path: record.relativePath,
                    line: offset + 1,
                    reason: "expected \(expectedColumns) columns, got \(fields.count)"
                )
            }
            try body(offset + 1, fields)
        }
    }
}
