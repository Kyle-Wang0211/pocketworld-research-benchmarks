import CoreVideo
import CryptoKit
import QuartzCore
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
    /// Deep enough to ride out a filesystem stall instead of losing frames to
    /// one. Eight slots is 133 ms at 60 fps and a 168 ms stall was observed;
    /// sixty-four is a little over a second, at 177 MB of luma held at worst.
    /// This absorbs jitter, it does not hide loss -- an overflow is still
    /// counted and still invalidates the run.
    static let queueDepth = 64

    /// Refuse to start unless the device has the full recording plus this much
    /// headroom.
    ///
    /// The guard stays because running out of space mid-write leaves a truncated
    /// recording, which is strictly worse than a refusal: the operator has spent
    /// the time and the file cannot be replayed. But it was refusing 30 s
    /// captures by always projecting 300 s, and 2 GiB of slack on top of that
    /// made a device with 8.3 GiB free look unusable. The projection now follows
    /// the selected duration and the slack is the minimum that keeps the
    /// filesystem out of trouble.
    static let freeSpaceHeadroomBytes: Int64 = 512 * 1024 * 1024

    private let directory: URL
    private let framesDirectory: URL
    private var format: DeviceRecordingCameraFormat
    private let recordingID: String

    /// Serial, and explicitly user-initiated. At 60 fps this queue has 133 ms of
    /// slack across its eight slots, so letting the system deprioritise it costs
    /// frames directly.
    private let writeQueue = DispatchQueue(
        label: "com.kyle.viobench.recording.write",
        qos: .userInitiated
    )
    private let stateLock = NSLock()

    private var framesHandleDigest = SHA256()
    private var cameraIndexRows: [String] = []
    /// Both handles stay open for the life of the capture and are flushed after
    /// every frame, stream before index, exactly as pwva.dart does: an interrupt
    /// at any moment leaves a prefix that is self-consistent, because the index
    /// never names bytes the stream has not already committed.
    private let framesStream: FileHandle
    private let framesIndex: FileHandle
    private var streamOffset = 0

    /// Production's archive parameters, from capture_archive_service.dart.
    static let archiveGOP: Int32 = 8
    static let archiveQuality = 0.65
    /// Production's default. capture_archive_service.dart constructs
    /// AppleHevcEncoder without overriding powerEfficient, and its default is
    /// true -- the low-power encode path kept for thermal headroom.
    static let archivePowerEfficient: Int32 = 1

    private let encoder: OpaquePointer
    /// Chroma for the encoder. The bench records luma only -- the arms consume
    /// luma and nothing else -- so a neutral plane stands in for the chroma the
    /// capture never kept.
    private let neutralChroma: Data
    private var gopID = -1
    /// Set before the write queue is drained in finish(). A frame arriving after
    /// this must not be written into an archive that is being sealed: a late
    /// ARKit delivery did exactly that and left a manifest describing 1619
    /// frames over a stream holding 1616.
    private var sealed = false
    private var lateAfterSeal = 0
    private var intrinsicsRows: [String] = []
    private var focalMinimum = Double.greatestFiniteMagnitude
    private var focalMaximum = 0.0
    private var imuRows: [String] = []
    private var arkitPoseRows: [String] = []

    private var frameCount = 0
    private var framesTotalBytes: Int64 = 0
    private var lossCount = 0
    private var lossFormatMismatch = 0
    private var lossWriteQueueFull = 0
    private var lossWriteError = 0
    private var peakInFlight = 0
    private var slowestWriteMilliseconds: Double = 0
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
            at: directory,
            withIntermediateDirectories: true
        )
        // Create both files, then hold the handles open for the whole capture.
        let streamURL = directory.appendingPathComponent(
            DeviceRecordingManifest.framesStreamPath
        )
        let indexURL = directory.appendingPathComponent(
            DeviceRecordingManifest.framesIndexPath
        )
        FileManager.default.createFile(atPath: streamURL.path, contents: nil)
        FileManager.default.createFile(atPath: indexURL.path, contents: nil)
        self.framesStream = try FileHandle(forWritingTo: streamURL)
        self.framesIndex = try FileHandle(forWritingTo: indexURL)
        guard let encoder = pw_vt_create_ex(
            Int32(format.width),
            Int32(format.height),
            Self.archiveGOP,
            Self.archiveQuality,
            0,
            Self.archivePowerEfficient
        ) else {
            throw DeviceRecordingError.encoderUnavailable
        }
        self.encoder = encoder
        self.neutralChroma = Data(repeating: 128, count: format.width * format.height / 2)
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
    /// Records this frame's intrinsics, then cross-checks the first frame's.
    /// Every frame is kept because production keeps every frame's: its per-photo
    /// sidecar pins `intrinsics_fxfycxcy` to the snapshot the pose came from.
    /// `source` names where the numbers came from, because a reader must never
    /// have to infer it: the ARKit arm reports `ARFrame.camera.intrinsics`, the
    /// AVFoundation transport reports the camera's own
    /// `kCMSampleBufferAttachmentKey_CameraIntrinsicMatrix`. `expected` is what
    /// the observation is compared against in `intrinsics_observed.json`;
    /// the default is upstream's 640x480 config scaled to the 1920x1440
    /// scoring format, which is meaningless for a frame that is natively
    /// 640x480, so the native path passes the unscaled values instead.
    func recordIntrinsics(
        _ reported: CameraIntrinsics,
        timestampSeconds: Double,
        source: String = "ARFrame.camera.intrinsics",
        expected: CameraIntrinsics = ARKitIntrinsicsCrossCheck.expectedScoringIntrinsics
    ) throws {
        stateLock.lock()
        defer { stateLock.unlock() }

        if reported.fx.isFinite, reported.fx > 0 {
            focalMinimum = min(focalMinimum, reported.fx)
            focalMaximum = max(focalMaximum, reported.fx)
        }
        // Same keys as the production sidecar, so a consumer that reads one
        // reads the other.
        intrinsicsRows.append(
            "{\"t\":\(timestampSeconds),\"intrinsics_fxfycxcy\":"
                + "[\(reported.fx),\(reported.fy),\(reported.cx),\(reported.cy)]}"
        )

        guard intrinsics == nil else { return }

        // Persist what the device actually reported before judging it. The first
        // cross-check failure discarded the very numbers needed to understand it,
        // leaving only "they disagree" -- which says nothing about whether the
        // scaling premise is wrong, the format is cropped, or the tolerance is
        // simply too tight.
        let verdict = ARKitIntrinsicsCrossCheck.check(
            arkitReported: reported,
            frameWidth: format.width,
            frameHeight: format.height
        )
        let observed: [String: Any] = [
            "intrinsics_source": source,
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
            // What ARKit actually handed us, so the format is evidence in the
            // artifact rather than something inferred from cx afterwards.
            "frame_width_from_principal_point": reported.cx * 2,
            "frame_height_from_principal_point": reported.cy * 2,
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
            source: source,
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
            stateLock.lock()
            lossCount += 1
            lossFormatMismatch += 1
            stateLock.unlock()
            return
        }
        enqueue(luma: luma, timestampNanoseconds: timestampNanoseconds)
    }

    /// Records a grayscale plane the caller already holds.
    ///
    /// The AVFoundation transport reaches gray before the recorder does: it
    /// captures 32BGRA and converts through upstream's own
    /// `cvtColor(BGRA2GRAY)` into a pooled plane, and that plane -- not a
    /// pixel buffer -- is what the engine is handed. Recording from it is the
    /// point: the file then holds the exact bytes the engine consumed, rather
    /// than a second conversion of the same frame that could differ from it.
    ///
    /// The caller must copy before handing the lease to the engine. A lease is
    /// released by whoever consumes the frame, so reading its storage after
    /// handoff is a use-after-free; this takes `Data` so that copy is explicit
    /// at the call site rather than implied here.
    func appendLuma(_ luma: Data, timestampNanoseconds: Int64) {
        guard luma.count == format.bytesPerFrame else {
            stateLock.lock()
            lossCount += 1
            lossFormatMismatch += 1
            stateLock.unlock()
            return
        }
        enqueue(luma: luma, timestampNanoseconds: timestampNanoseconds)
    }

    private func enqueue(luma: Data, timestampNanoseconds: Int64) {
        stateLock.lock()
        guard !sealed else {
            lateAfterSeal += 1
            stateLock.unlock()
            return
        }
        guard inFlight < Self.queueDepth else {
            // Backpressure is loss, and loss invalidates. It is never absorbed by
            // growing the queue or by skipping ahead.
            lossCount += 1
            lossWriteQueueFull += 1
            stateLock.unlock()
            return
        }
        let index = frameCount
        frameCount += 1
        inFlight += 1
        peakInFlight = max(peakInFlight, inFlight)
        cameraIndexRows.append("\(timestampNanoseconds),\(index)")
        stateLock.unlock()

        writeQueue.async { [weak self] in
            guard let self else { return }
            let writeStart = CACurrentMediaTime()
            do {
                // Stream first, then the index row -- pwva.dart's order, so an
                // interrupted capture leaves a prefix the index never
                // over-claims. The payload is the raw plane.
                //
                // Encoding was tried in both places production suggests and
                // neither survives this requirement. In the capture path a
                // hardware encode cost 127 ms on one frame against a 16.6 ms
                // budget and lost 73 to backpressure. After the capture, as
                // production does it, 1800 frames took minutes and iOS
                // suspended the app partway, leaving a run with no manifest at
                // all. Production never faces this: it archives a few dozen
                // shutter stills, not every frame at 60 fps, so there is no
                // production answer here to copy. Transcoding now happens off
                // the device, where nothing suspends it.
                let offset = self.streamOffset
                try self.framesStream.write(contentsOf: luma)
                try self.framesStream.synchronize()
                let row = "{\"frame\":\(index),\"offset\":\(offset)," +
                    "\"len\":\(luma.count),\"keyframe\":true,\"gop\":\(index)}\n"
                try self.framesIndex.write(contentsOf: Data(row.utf8))
                try self.framesIndex.synchronize()
                let elapsed = (CACurrentMediaTime() - writeStart) * 1000
                self.stateLock.lock()
                self.streamOffset = offset + luma.count
                self.slowestWriteMilliseconds = max(self.slowestWriteMilliseconds, elapsed)
                self.framesHandleDigest.update(data: luma)
                self.framesTotalBytes += Int64(luma.count)
                self.inFlight -= 1
                self.stateLock.unlock()
            } catch {
                self.stateLock.lock()
                self.lossCount += 1
                self.lossWriteError += 1
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

    /// Encodes one luma plane through production's encoder.
    private func encode(luma: Data, index: Int) throws -> (bytes: Data, keyframe: Bool) {
        var out: UnsafeMutablePointer<UInt8>?
        var length: Int64 = 0
        var keyframe: Int32 = 0
        let status: Int32 = luma.withUnsafeBytes { y in
            neutralChroma.withUnsafeBytes { uv in
                pw_vt_encode_nv12(
                    encoder,
                    y.bindMemory(to: UInt8.self).baseAddress,
                    uv.bindMemory(to: UInt8.self).baseAddress,
                    Int64(index) * 1000 / Int64(format.nominalFPS),
                    1000 / Int64(format.nominalFPS),
                    &out,
                    &length,
                    &keyframe
                )
            }
        }
        guard status == 0, let out, length > 0 else {
            throw DeviceRecordingError.encodeFailed(frame: index, status: Int(status))
        }
        defer { pw_vt_free(out) }
        return (Data(bytes: out, count: Int(length)), keyframe != 0)
    }

    deinit {
        pw_vt_destroy(encoder)
    }

    // MARK: - Finish

    /// Drains the write queue and seals the manifest. Any loss makes the
    /// recording invalid; the manifest still records the count so the failure is
    /// legible rather than silent.
    @discardableResult
    func finish() throws -> DeviceRecordingManifest {
        // Seal before draining. Otherwise a frame delivered while the drain is
        // running is accepted, written, and counted after the totals have been
        // read -- which is how a manifest came to describe 1619 frames over a
        // stream that held 1616.
        stateLock.lock()
        sealed = true
        stateLock.unlock()
        writeQueue.sync {}

        stateLock.lock()
        if let firstError { stateLock.unlock(); throw firstError }
        let manifestFrameCount = frameCount
        let archiveBytes = framesTotalBytes
        let archiveDigest = Self.hex(framesHandleDigest.finalize())
        // Every counter is snapshotted here, under the same lock, for the same
        // reason the totals are: read outside it they are a race, and a manifest
        // reported one write error on a run that had none and could not have had
        // one -- a write failure sets firstError, which makes finish throw.
        let losses = lossCount
        let lossesFormat = lossFormatMismatch
        let lossesQueueFull = lossWriteQueueFull
        let lossesWriteError = lossWriteError
        let peak = peakInFlight
        let slowestWrite = slowestWriteMilliseconds
        let lateSeal = lateAfterSeal
        let cameraCSV = (["timestamp_ns,relative_path"] + cameraIndexRows).joined(separator: "\n") + "\n"
        let imuCSV = (["timestamp_ns,wx,wy,wz,ax,ay,az"] + imuRows).joined(separator: "\n") + "\n"
        let poseTUM = arkitPoseRows.joined(separator: "\n") + "\n"
        let intrinsicsJSONL = intrinsicsRows.joined(separator: "\n") + "\n"
        let focalLow = focalMinimum == .greatestFiniteMagnitude ? 0 : focalMinimum
        let focalHigh = focalMaximum
        let capturedIntrinsics = intrinsics
        stateLock.unlock()

        guard let capturedIntrinsics else {
            // No intrinsics means no frame ever arrived. Reporting that as a
            // failed cross-check named the wrong cause and cost an investigation.
            throw DeviceRecordingError.noFramesCaptured
        }

        var files: [DeviceRecordingFile] = []
        for (role, path, contents) in [
            (DeviceRecordingFileRole.cameraIndex, "camera_index.csv", cameraCSV),
            (DeviceRecordingFileRole.intrinsicsIndex, "intrinsics.jsonl", intrinsicsJSONL),
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
        try framesStream.close()
        try framesIndex.close()

        // The stream's hash is the digest already accumulated frame by frame as
        // they were written -- the same bytes in the same order -- so it is
        // taken from there rather than by reading the file back. pwva.dart
        // accumulates its stream hash the same way while writing. Re-reading
        // instead left a 30 s capture stuck in finalize hashing 4.55 GB.
        files.append(DeviceRecordingFile(
            role: .framesStream,
            relativePath: DeviceRecordingManifest.framesStreamPath,
            byteCount: archiveBytes,
            sha256: archiveDigest
        ))
        let indexURL = directory.appendingPathComponent(
            DeviceRecordingManifest.framesIndexPath
        )
        let indexData = try Data(contentsOf: indexURL)
        files.append(DeviceRecordingFile(
            role: .framesIndex,
            relativePath: DeviceRecordingManifest.framesIndexPath,
            byteCount: Int64(indexData.count),
            sha256: Self.hex(SHA256.hash(data: indexData))
        ))
        files.sort { $0.relativePath < $1.relativePath }

        let manifest = DeviceRecordingManifest(
            schemaVersion: DeviceRecordingManifest.supportedSchemaVersion,
            recordingID: recordingID,
            camera: format,
            intrinsics: capturedIntrinsics,
            frameCount: manifestFrameCount,
            imuSampleCount: imuRows.count,
            framesDigestSHA256: archiveDigest,
            framesTotalByteCount: archiveBytes,
            lossCount: losses,
            lossFormatMismatch: lossesFormat,
            lossWriteQueueFull: lossesQueueFull,
            lossWriteError: lossesWriteError,
            peakInFlight: peak,
            slowestWriteMilliseconds: slowestWrite,
            focalLengthMinimum: focalLow,
            focalLengthMaximum: focalHigh,
            lateFramesAfterSeal: lateSeal,
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
