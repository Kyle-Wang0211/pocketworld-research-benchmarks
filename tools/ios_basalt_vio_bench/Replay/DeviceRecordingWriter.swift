import CoreVideo
import CryptoKit
import Foundation

/// Persists one capture so every arm can be fed the identical trajectory.
///
/// Three rules shape this writer:
///
/// 1. **It must not block the capture callback.** `ARSession` delivers frames on
///    its delegate queue; a 2.76 MB synchronous file write there at 30 Hz would
///    stall ARKit itself, so the arm being measured would be measuring the
///    recorder. Frames are copied into a bounded queue and written on a private
///    serial queue.
/// 2. **A drop is a failure, not a shorter recording.** If the queue is full the
///    frame is counted as a loss and the recording is invalid. Silently skipping
///    a frame would leave a plausible file that no longer matches what ARKit saw.
/// 3. **No encoding, ever.** Raw luma only. An encoder on the capture path costs
///    the arm being measured, and a lossy one changes the pixels every candidate
///    is then scored on.
final class DeviceRecordingWriter: @unchecked Sendable {

    /// Bounded at eight frames (~22 MB at 1920x1440). Deep enough to absorb a
    /// filesystem hiccup, shallow enough that sustained write starvation is
    /// reported as loss instead of being hidden by an ever-growing buffer.
    static let queueDepth = 8

    /// Refuse to start unless the device has the full recording plus this much
    /// headroom. Running out of space mid-capture wastes the operator's time and
    /// leaves a truncated file.
    static let freeSpaceHeadroomBytes: Int64 = 2 * 1024 * 1024 * 1024

    private let directory: URL
    private let framesDirectory: URL
    private var format: DeviceRecordingCameraFormat
    private let recordingID: String

    private let writeQueue = DispatchQueue(label: "com.kyle.viobench.recording.write")
    private let stateLock = NSLock()

    private var framesHandleDigest = SHA256()
    private var cameraIndexRows: [String] = []
    private var imuRows: [String] = []
    private var arkitPoseRows: [String] = []

    private var frameCount = 0
    private var framesTotalBytes: Int64 = 0
    private var lossCount = 0
    private var inFlight = 0
    private var firstError: Error?

    private var intrinsics: DeviceRecordingIntrinsics?

    init(
        directory: URL,
        recordingID: String,
        format: DeviceRecordingCameraFormat = .scoring
    ) throws {
        // The manifest must state the rate the session actually selected. ARKit's
        // 1920x1440 format runs at 60 fps on this device, and a manifest that
        // hardcoded 30 both misdescribed the recording and halved every storage
        // projection built on it.
        self.directory = directory
        self.framesDirectory = directory.appendingPathComponent(
            DeviceRecordingManifest.framesDirectory
        )
        self.format = format
        self.recordingID = recordingID
        try FileManager.default.createDirectory(
            at: framesDirectory,
            withIntermediateDirectories: true
        )
    }

    // MARK: - Preflight

    /// Bytes a recording of `seconds` will occupy, so the operator is told before
    /// the capture rather than after it fails.
    static func projectedByteCount(
        seconds: Double,
        format: DeviceRecordingCameraFormat = .scoring
    ) -> Int64 {
        Int64((seconds * format.nominalFPS).rounded(.up)) * Int64(format.bytesPerFrame)
    }

    static func checkFreeSpace(
        at url: URL,
        requiredBytes: Int64
    ) throws {
        let values = try url.resourceValues(
            forKeys: [.volumeAvailableCapacityForImportantUsageKey]
        )
        let available = Int64(values.volumeAvailableCapacityForImportantUsage ?? 0)
        let needed = requiredBytes + freeSpaceHeadroomBytes
        guard available >= needed else {
            throw DeviceRecordingError.insufficientFreeSpace(
                requiredBytes: needed,
                availableBytes: available
            )
        }
    }

    /// The selected frame rate is only knowable once the session has started, so
    /// the manifest is corrected then rather than shipping a constant. A manifest
    /// claiming 30 fps for a 60 fps recording misdescribes the input and halves
    /// every storage projection derived from it.
    func setNominalFPS(_ fps: Double) {
        guard fps > 0 else { return }
        stateLock.lock()
        format.nominalFPS = fps
        stateLock.unlock()
    }

    // MARK: - Intrinsics

    /// Recorded once, from the first frame that reports them. The cross-check
    /// runs here so a mismatched format halts before the operator spends five
    /// minutes on an unusable capture.
    func recordIntrinsicsIfNeeded(_ reported: CameraIntrinsics) throws {
        stateLock.lock()
        defer { stateLock.unlock() }
        guard intrinsics == nil else { return }

        // Persist what the device actually reported before judging it. The first
        // cross-check failure discarded the very numbers needed to understand it,
        // leaving only "they disagree" -- which says nothing about whether the
        // scaling premise is wrong, the format is cropped, or the tolerance is
        // simply too tight.
        let verdict = ARKitIntrinsicsCrossCheck.check(arkitReported: reported)
        let expected = ARKitIntrinsicsCrossCheck.expectedScoringIntrinsics
        let observed: [String: Any] = [
            "arkit_reported": ["fx": reported.fx, "fy": reported.fy,
                               "cx": reported.cx, "cy": reported.cy],
            "expected_from_upstream_x3": ["fx": expected.fx, "fy": expected.fy,
                                          "cx": expected.cx, "cy": expected.cy],
            "delta_pixels": ["fx": reported.fx - expected.fx,
                             "fy": reported.fy - expected.fy,
                             "cx": reported.cx - expected.cx,
                             "cy": reported.cy - expected.cy],
            "focal_relative_tolerance": ARKitIntrinsicsCrossCheck.focalRelativeTolerance,
            "principal_point_tolerance_pixels":
                ARKitIntrinsicsCrossCheck.principalPointToleranceP,
            "focal_relative_delta": [
                "fx": expected.fx > 0 ? (reported.fx - expected.fx) / expected.fx : .nan,
                "fy": expected.fy > 0 ? (reported.fy - expected.fy) / expected.fy : .nan,
            ],
            "agrees": verdict.reason == nil,
            "reason": verdict.reason ?? "agrees",
        ]
        if let data = try? JSONSerialization.data(
            withJSONObject: observed, options: [.prettyPrinted, .sortedKeys]
        ) {
            try? data.write(
                to: directory.appendingPathComponent("intrinsics_observed.json"),
                options: .atomic
            )
        }

        guard case .agrees(let scoring) = verdict else {
            throw DeviceRecordingError.intrinsicsCrossCheckFailed
        }
        intrinsics = DeviceRecordingIntrinsics(
            fx: scoring.fx,
            fy: scoring.fy,
            cx: scoring.cx,
            cy: scoring.cy,
            source: "ARFrame.camera.intrinsics",
            crossCheckPassed: true
        )
    }

    // MARK: - Ingest

    /// Copies the luma plane out of an `ARFrame.capturedImage` and enqueues it.
    ///
    /// The copy happens on the caller's thread because the pixel buffer is only
    /// valid for the duration of the callback; it is a single memcpy per row,
    /// with no encoding and no format conversion.
    func appendFrame(
        pixelBuffer: CVPixelBuffer,
        timestampNanoseconds: Int64
    ) {
        guard let luma = Self.copyLumaPlane(pixelBuffer, expected: format) else {
            stateLock.lock(); lossCount += 1; stateLock.unlock()
            return
        }

        stateLock.lock()
        guard inFlight < Self.queueDepth else {
            // Backpressure is loss, and loss invalidates. It is never absorbed by
            // growing the queue or by skipping ahead.
            lossCount += 1
            stateLock.unlock()
            return
        }
        let index = frameCount
        frameCount += 1
        inFlight += 1
        cameraIndexRows.append("\(timestampNanoseconds),\(DeviceRecordingManifest.frameRelativePath(index: index))")
        stateLock.unlock()

        writeQueue.async { [weak self] in
            guard let self else { return }
            let url = self.directory.appendingPathComponent(
                DeviceRecordingManifest.frameRelativePath(index: index)
            )
            do {
                try luma.write(to: url, options: .atomic)
                self.stateLock.lock()
                // The digest covers frames in capture order, which the serial
                // write queue preserves.
                self.framesHandleDigest.update(data: luma)
                self.framesTotalBytes += Int64(luma.count)
                self.inFlight -= 1
                self.stateLock.unlock()
            } catch {
                self.stateLock.lock()
                self.lossCount += 1
                self.inFlight -= 1
                if self.firstError == nil { self.firstError = error }
                self.stateLock.unlock()
            }
        }
    }

    func appendIMU(
        timestampNanoseconds: Int64,
        gyroscope: (x: Double, y: Double, z: Double),
        acceleration: (x: Double, y: Double, z: Double)
    ) {
        let row = "\(timestampNanoseconds),\(gyroscope.x),\(gyroscope.y),\(gyroscope.z),"
            + "\(acceleration.x),\(acceleration.y),\(acceleration.z)"
        stateLock.lock(); imuRows.append(row); stateLock.unlock()
    }

    /// ARKit's own trajectory over these frames: a same-input system reference,
    /// recorded so the comparison is against the identical motion.
    func appendARKitPose(timestampNanoseconds: Int64, tumRow: String) {
        stateLock.lock(); arkitPoseRows.append(tumRow); stateLock.unlock()
    }

    // MARK: - Finish

    /// Drains the write queue and seals the manifest. Any loss makes the
    /// recording invalid; the manifest still records the count so the failure is
    /// legible rather than silent.
    @discardableResult
    func finish() throws -> DeviceRecordingManifest {
        writeQueue.sync {}

        stateLock.lock()
        if let firstError { stateLock.unlock(); throw firstError }
        let digest = framesHandleDigest.finalize()
        let manifestFrameCount = frameCount
        let totalBytes = framesTotalBytes
        let losses = lossCount
        let cameraCSV = (["timestamp_ns,relative_path"] + cameraIndexRows).joined(separator: "\n") + "\n"
        let imuCSV = (["timestamp_ns,wx,wy,wz,ax,ay,az"] + imuRows).joined(separator: "\n") + "\n"
        let poseTUM = arkitPoseRows.joined(separator: "\n") + "\n"
        let capturedIntrinsics = intrinsics
        stateLock.unlock()

        guard let capturedIntrinsics else {
            throw DeviceRecordingError.intrinsicsCrossCheckFailed
        }

        var files: [DeviceRecordingFile] = []
        for (role, path, contents) in [
            (DeviceRecordingFileRole.cameraIndex, "camera_index.csv", cameraCSV),
            (DeviceRecordingFileRole.imuIndex, "imu.csv", imuCSV),
            (DeviceRecordingFileRole.arkitPoses, "arkit_poses.tum", poseTUM),
        ] {
            let data = Data(contents.utf8)
            try data.write(to: directory.appendingPathComponent(path), options: .atomic)
            files.append(DeviceRecordingFile(
                role: role,
                relativePath: path,
                byteCount: Int64(data.count),
                sha256: Self.hex(SHA256.hash(data: data))
            ))
        }
        files.sort { $0.relativePath < $1.relativePath }

        let manifest = DeviceRecordingManifest(
            schemaVersion: DeviceRecordingManifest.supportedSchemaVersion,
            recordingID: recordingID,
            camera: format,
            intrinsics: capturedIntrinsics,
            frameCount: manifestFrameCount,
            imuSampleCount: imuRows.count,
            framesDigestSHA256: Self.hex(digest),
            framesTotalByteCount: totalBytes,
            lossCount: losses,
            files: files
        )

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(manifest).write(
            to: directory.appendingPathComponent("recording_manifest.json"),
            options: .atomic
        )
        return manifest
    }

    // MARK: - Helpers

    /// Extracts the Y plane of a 420f biplanar buffer.
    ///
    /// `bytesPerRow` is frequently padded beyond `width`, so rows are copied
    /// individually; blitting the plane wholesale would embed the stride in the
    /// file and every replayed frame would be sheared.
    static func copyLumaPlane(
        _ pixelBuffer: CVPixelBuffer,
        expected: DeviceRecordingCameraFormat
    ) -> Data? {
        guard CVPixelBufferGetWidthOfPlane(pixelBuffer, 0) == expected.width,
              CVPixelBufferGetHeightOfPlane(pixelBuffer, 0) == expected.height else {
            return nil
        }
        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0) else {
            return nil
        }
        let stride = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0)
        var out = Data(count: expected.bytesPerFrame)
        out.withUnsafeMutableBytes { destination in
            guard let destinationBase = destination.baseAddress else { return }
            for row in 0..<expected.height {
                memcpy(
                    destinationBase.advanced(by: row * expected.width),
                    base.advanced(by: row * stride),
                    expected.width
                )
            }
        }
        return out
    }

    static func hex<D: Sequence>(_ digest: D) -> String where D.Element == UInt8 {
        digest.map { String(format: "%02x", $0) }.joined()
    }
}
