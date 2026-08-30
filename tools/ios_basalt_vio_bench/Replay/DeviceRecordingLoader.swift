import CryptoKit
import Foundation

/// Reads a raw luma frame back exactly as it was captured.
///
/// `GrayscaleImageLoader` decodes encoded images; recorded frames are not
/// encoded, so there is nothing to decode. The file *is* the plane, and the only
/// check that matters is that its length is exactly one frame -- a short or long
/// file means the recording is not what its manifest says.
enum RawLumaFrameLoader {
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

        let frames = try parseCameraIndex(
            record: cameraRecord,
            root: root,
            format: manifest.camera
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
        for record in files {
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
        for frame in frames {
            digest.update(data: try Data(contentsOf: frame.camera0ImageURL, options: .mappedIfSafe))
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

    private func parseCameraIndex(
        record: DeviceRecordingFile,
        root: URL,
        format: DeviceRecordingCameraFormat
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
            try rejectUnsafePath(fields[1])
            let url = root.appendingPathComponent(fields[1])
            // Structural check on every frame: present, and exactly one frame
            // long. Cheap enough to always run, and it is what catches a
            // truncated capture before it becomes a measurement.
            let attributes = try? FileManager.default.attributesOfItem(atPath: url.path)
            guard let size = attributes?[.size] as? Int64 else {
                throw DeviceRecordingError.missingFrame(fields[1])
            }
            guard size == Int64(format.bytesPerFrame) else {
                throw DeviceRecordingError.frameSizeMismatch(
                    path: fields[1], expected: format.bytesPerFrame, actual: Int(size)
                )
            }
            frames.append(EuRoCCameraFrame(
                timestampNanoseconds: timestamp,
                camera0ImageURL: url,
                camera1ImageURL: nil
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
