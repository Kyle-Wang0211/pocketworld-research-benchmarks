import AVFoundation
import CoreMedia
import CoreMotion
import CoreVideo
import Foundation

/// Hardware sensor transport only. This type never creates ARKit, reads a pose,
/// performs VIO policy, touches disk, or dispatches UI work from a callback.
public final class LiveSensorTransport: NSObject, @unchecked Sendable {
    public enum TransportError: Error, Equatable {
        case cameraPermissionDenied
        case cameraUnavailable
        case cameraFormatUnavailable(width: Int32, height: Int32, rateHz: Int32)
        case cannotCreateCameraInput
        case cannotAddCameraInput
        case cannotAddCameraOutput
        case gyroscopeUnavailable
        case accelerometerUnavailable
        case invalidHostClock
        case invalidLifecycle
    }

    public let configuration: SensorTransportConfiguration
    public let clockMapper: MonotonicClockMapper
    public let imuDeliveryMode: IMUDeliveryMode
    public let accounting = SensorTransportAccounting()
    public let cameraHandoff: BoundedNonblockingHandoff<MonochromeCameraFrame>
    public let imuHandoff: BoundedNonblockingHandoff<PairedIMUSample>
    public let xrslamSensorHandoff: BoundedNonblockingHandoff<XRSLAMLiveSensorEvent>

    private let captureSession = AVCaptureSession()
    private let videoOutput = AVCaptureVideoDataOutput()
    private let motionManager = CMMotionManager()
    private let cameraCallbackQueue = DispatchQueue(
        label: "com.kyle.viobench.sensor.camera",
        qos: .userInitiated
    )
    private let controlQueue = DispatchQueue(
        label: "com.kyle.viobench.sensor.control",
        qos: .userInitiated
    )
    private lazy var motionCallbackQueue: OperationQueue = {
        let queue = OperationQueue()
        queue.name = "com.kyle.viobench.sensor.motion"
        queue.qualityOfService = .userInitiated
        queue.maxConcurrentOperationCount = 1
        queue.underlyingQueue = cameraCallbackQueue
        return queue
    }()

    private let lifecycleLock = NSLock()
    private let imuAssemblerLock = NSLock()
    private var lifecycle = SensorTransportLifecycle()
    private var notificationTokens: [NSObjectProtocol] = []
    private var cameraTimestamps = TimestampSequenceValidator()
    private var imuAssembler: GyroDrivenIMUAssembler
    private var captureFormatReceipt: LiveCaptureFormatReceipt?

    public init(
        configuration: SensorTransportConfiguration = .benchmark,
        imuDeliveryMode: IMUDeliveryMode = .basaltGyroDrivenPaired,
        clockMapper: MonotonicClockMapper
    ) {
        self.configuration = configuration
        self.imuDeliveryMode = imuDeliveryMode
        self.clockMapper = clockMapper
        cameraHandoff = BoundedNonblockingHandoff(
            capacity: configuration.cameraQueueCapacity
        )
        imuHandoff = BoundedNonblockingHandoff(
            capacity: configuration.imuQueueCapacity
        )
        xrslamSensorHandoff = BoundedNonblockingHandoff(
            capacity: configuration.cameraQueueCapacity
                + configuration.imuQueueCapacity * 2
        )
        imuAssembler = GyroDrivenIMUAssembler(
            pendingGyroscopeCapacity: configuration.pendingGyroscopeCapacity
        )
        super.init()
    }

    /// Samples the Core Media host clock around `systemUptime`, creating the
    /// sole production clock mapping used by both capture paths.
    public convenience init(
        configuration: SensorTransportConfiguration = .benchmark,
        imuDeliveryMode: IMUDeliveryMode = .basaltGyroDrivenPaired
    ) throws {
        let hostBefore = CMTimeGetSeconds(CMClockGetTime(CMClockGetHostTimeClock()))
        let uptime = ProcessInfo.processInfo.systemUptime
        let hostAfter = CMTimeGetSeconds(CMClockGetTime(CMClockGetHostTimeClock()))
        let hostAnchor = (hostBefore + hostAfter) * 0.5
        let nanoseconds = hostAnchor * 1_000_000_000.0
        guard hostAnchor.isFinite,
              hostAnchor >= 0,
              nanoseconds.isFinite,
              nanoseconds >= 0,
              nanoseconds < Double(UInt64.max) else {
            throw TransportError.invalidHostClock
        }
        self.init(
            configuration: configuration,
            imuDeliveryMode: imuDeliveryMode,
            clockMapper: MonotonicClockMapper(
                cameraHostTimeAnchorSeconds: hostAnchor,
                coreMotionUptimeAnchorSeconds: uptime,
                monotonicAnchorNanoseconds: UInt64(
                    nanoseconds.rounded(.toNearestOrAwayFromZero)
                )
            )
        )
    }

    /// Display-only tap on frames already handed to the engine.
    var previewTap: PreviewFrameTap?

    public var state: SensorTransportLifecycle.State {
        lifecycleLock.withLock { lifecycle.state }
    }

    /// Configures and starts both hardware producers. Call this from a control
    /// thread; `AVCaptureSession.startRunning()` is intentionally not hidden in
    /// a sensor callback or main/UI dispatch.
    public func start() throws {
        try transition(to: .starting)
        do {
            try configureCamera()
            registerCaptureNotifications()
            try startMotionUpdates()
            captureSession.startRunning()
            try transition(to: .running)
        } catch {
            moveToFailedIfPossible()
            stop()
            throw error
        }
    }

    /// Stops producers first, then seals both channels. Items accepted
    /// before sealing remain available until the consumer drains them.
    public func stop() {
        let shouldStop = lifecycleLock.withLock { () -> Bool in
            switch lifecycle.state {
            case .starting, .running, .interrupted, .failed:
                try? lifecycle.transition(to: .stopping)
                return true
            case .idle, .stopping, .sealed, .drained:
                return false
            }
        }
        guard shouldStop else { return }

        motionManager.stopGyroUpdates()
        motionManager.stopAccelerometerUpdates()
        captureSession.stopRunning()
        motionCallbackQueue.waitUntilAllOperationsAreFinished()
        cameraCallbackQueue.sync {}
        unregisterCaptureNotifications()

        if imuDeliveryMode == .basaltGyroDrivenPaired {
            _ = imuAssemblerLock.withLock { imuAssembler.seal() }
        }
        cameraHandoff.seal()
        imuHandoff.seal()
        xrslamSensorHandoff.seal()
        try? transition(to: .sealed)
    }

    public func drainCamera(maxCount: Int) -> BoundedNonblockingHandoff<MonochromeCameraFrame>.DrainBatch {
        let batch = cameraHandoff.drain(maxCount: maxCount)
        updateDrainedStateIfNeeded()
        return batch
    }

    /// This is the only estimator-facing IMU channel. Each item has official
    /// gyro-driven time semantics and an interpolated acceleration value.
    public func drainIMU(maxCount: Int) -> BoundedNonblockingHandoff<PairedIMUSample>.DrainBatch {
        let batch = imuHandoff.drain(maxCount: maxCount)
        updateDrainedStateIfNeeded()
        return batch
    }

    /// Official XRSLAM live ordering: all three sensor callback types leave
    /// one serial producer queue through one bounded handoff.
    public func drainXRSLAMSensorEvents(
        maxCount: Int
    ) -> BoundedNonblockingHandoff<XRSLAMLiveSensorEvent>.DrainBatch {
        let batch = xrslamSensorHandoff.drain(maxCount: maxCount)
        updateDrainedStateIfNeeded()
        return batch
    }

    public func snapshot() -> LiveSensorTransportSnapshot {
        LiveSensorTransportSnapshot(
            state: state,
            accounting: accounting.snapshot(),
            imuDeliveryMode: imuDeliveryMode,
            imuAssembly: imuAssemblerLock.withLock { imuAssembler.receipt },
            cameraHandoff: cameraHandoff.snapshot(),
            imuHandoff: imuHandoff.snapshot(),
            xrslamSensorHandoff: xrslamSensorHandoff.snapshot(),
            captureFormat: lifecycleLock.withLock { captureFormatReceipt }
        )
    }

    private func configureCamera() throws {
        guard AVCaptureDevice.authorizationStatus(for: .video) == .authorized else {
            throw TransportError.cameraPermissionDenied
        }
        guard let device = AVCaptureDevice.default(
            .builtInWideAngleCamera,
            for: .video,
            position: .back
        ) else {
            throw TransportError.cameraUnavailable
        }

        let input: AVCaptureDeviceInput
        do {
            input = try AVCaptureDeviceInput(device: device)
        } catch {
            throw TransportError.cannotCreateCameraInput
        }

        let supportedPixelFormats = videoOutput.availableVideoPixelFormatTypes
        let fullRange = kCVPixelFormatType_420YpCbCr8BiPlanarFullRange
        guard supportedPixelFormats.contains(fullRange) else {
            throw TransportError.cameraFormatUnavailable(
                width: configuration.cameraWidth,
                height: configuration.cameraHeight,
                rateHz: configuration.cameraRateHz
            )
        }

        captureSession.beginConfiguration()
        var configurationIsOpen = true
        defer {
            if configurationIsOpen { captureSession.commitConfiguration() }
        }
        guard captureSession.canSetSessionPreset(.vga640x480) else {
            throw TransportError.cameraFormatUnavailable(
                width: configuration.cameraWidth,
                height: configuration.cameraHeight,
                rateHz: configuration.cameraRateHz
            )
        }
        captureSession.sessionPreset = .vga640x480

        guard captureSession.canAddInput(input) else {
            throw TransportError.cannotAddCameraInput
        }
        captureSession.addInput(input)

        videoOutput.alwaysDiscardsLateVideoFrames = true
        videoOutput.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String: fullRange,
            kCVPixelBufferWidthKey as String: Int(configuration.cameraWidth),
            kCVPixelBufferHeightKey as String: Int(configuration.cameraHeight),
        ]
        videoOutput.setSampleBufferDelegate(self, queue: cameraCallbackQueue)
        guard captureSession.canAddOutput(videoOutput) else {
            throw TransportError.cannotAddCameraOutput
        }
        captureSession.addOutput(videoOutput)

        guard let connection = videoOutput.connection(with: .video),
              connection.isVideoRotationAngleSupported(0) else {
            throw TransportError.cameraFormatUnavailable(
                width: configuration.cameraWidth,
                height: configuration.cameraHeight,
                rateHz: configuration.cameraRateHz
            )
        }
        connection.videoRotationAngle = 0
        if connection.isVideoStabilizationSupported {
            connection.preferredVideoStabilizationMode = .off
        }

        // Match XRSLAM's pinned sample by letting the VGA session preset choose
        // the active format. `device.formats.first` is deliberately forbidden:
        // its ordering is not a stable experiment identity.
        captureSession.commitConfiguration()
        configurationIsOpen = false

        do {
            try device.lockForConfiguration()
            defer { device.unlockForConfiguration() }
            let format = device.activeFormat
            let dimensions = CMVideoFormatDescriptionGetDimensions(
                format.formatDescription
            )
            guard dimensions.width == configuration.cameraWidth,
                  dimensions.height == configuration.cameraHeight,
                  let range = format.videoSupportedFrameRateRanges.first(where: {
                      $0.minFrameRate <= Double(configuration.cameraRateHz)
                          && $0.maxFrameRate >= Double(configuration.cameraRateHz)
                  }) else {
                throw TransportError.cameraFormatUnavailable(
                    width: configuration.cameraWidth,
                    height: configuration.cameraHeight,
                    rateHz: configuration.cameraRateHz
                )
            }
            let duration = CMTime(value: 1, timescale: configuration.cameraRateHz)
            device.activeVideoMinFrameDuration = duration
            device.activeVideoMaxFrameDuration = duration
            let receipt = LiveCaptureFormatReceipt(
                cameraDeviceType: device.deviceType.rawValue,
                activeFormatIndex: device.formats.firstIndex(where: { $0 === format }) ?? -1,
                activeFormatMediaSubtype: LiveCaptureFormatReceipt.fourCC(
                    CMFormatDescriptionGetMediaSubType(format.formatDescription)
                ),
                outputPixelFormat: LiveCaptureFormatReceipt.fourCC(fullRange),
                width: dimensions.width,
                height: dimensions.height,
                selectedFramesPerSecond: configuration.cameraRateHz,
                supportedFrameRateRange: "\(range.minFrameRate)...\(range.maxFrameRate)",
                fieldOfViewDegrees: Double(format.videoFieldOfView),
                zoomFactor: Double(device.videoZoomFactor),
                rotationDegrees: connection.videoRotationAngle,
                preferredStabilizationMode: Int(connection.preferredVideoStabilizationMode.rawValue),
                activeStabilizationMode: Int(connection.activeVideoStabilizationMode.rawValue),
                sessionPreset: AVCaptureSession.Preset.vga640x480.rawValue,
                grayscaleConversion: "nv12_full_range_luma_plane_direct",
                xrslamPixelPipelineDivergence: "pinned_xrslam_sample_requests_32bgra_then_opencv_bgra2gray"
            )
            lifecycleLock.withLock { captureFormatReceipt = receipt }
        } catch {
            throw TransportError.cameraFormatUnavailable(
                width: configuration.cameraWidth,
                height: configuration.cameraHeight,
                rateHz: configuration.cameraRateHz
            )
        }
    }

    private func startMotionUpdates() throws {
        guard motionManager.isGyroAvailable else {
            throw TransportError.gyroscopeUnavailable
        }
        guard motionManager.isAccelerometerAvailable else {
            throw TransportError.accelerometerUnavailable
        }

        let interval = 1.0 / configuration.motionRateHz
        motionManager.gyroUpdateInterval = interval
        motionManager.accelerometerUpdateInterval = interval
        motionManager.startGyroUpdates(to: motionCallbackQueue) { [weak self] data, error in
            self?.handleGyroscope(data, error: error)
        }
        motionManager.startAccelerometerUpdates(to: motionCallbackQueue) { [weak self] data, error in
            self?.handleAccelerometer(data, error: error)
        }
    }

    private func handleGyroscope(_ data: CMGyroData?, error: Error?) {
        if error != nil {
            accounting.recordMotionError()
            failAndScheduleStop()
            return
        }
        guard let data else { return }
        accounting.recordGyroscopeInput()
        guard let timestamp = try? clockMapper.motionNanoseconds(
            uptimeSeconds: data.timestamp
        ) else {
            accounting.recordMotionError()
            failAndScheduleStop()
            return
        }
        let sample = CoreMotionIMUConversion.gyroscopeRadiansPerSecond(
            timestampNanoseconds: timestamp,
            x: data.rotationRate.x,
            y: data.rotationRate.y,
            z: data.rotationRate.z
        )
        if imuDeliveryMode == .xrslamRawSeparateEvents {
            xrslamSensorHandoff.offer(.imu(.gyroscope(sample)))
            return
        }
        let batch = imuAssemblerLock.withLock { imuAssembler.ingestGyroscope(sample) }
        processIMUAssemblyBatch(batch)
    }

    private func handleAccelerometer(_ data: CMAccelerometerData?, error: Error?) {
        if error != nil {
            accounting.recordMotionError()
            failAndScheduleStop()
            return
        }
        guard let data else { return }
        accounting.recordAccelerometerInput()
        guard let timestamp = try? clockMapper.motionNanoseconds(
            uptimeSeconds: data.timestamp
        ) else {
            accounting.recordMotionError()
            failAndScheduleStop()
            return
        }
        if imuDeliveryMode == .xrslamRawSeparateEvents {
            xrslamSensorHandoff.offer(
                .imu(
                    .acceleration(
                        MotionVectorSample(
                            timestampNanoseconds: timestamp,
                            x: data.acceleration.x,
                            y: data.acceleration.y,
                            z: data.acceleration.z
                        )
                    )
                )
            )
            return
        }
        let sample = CoreMotionIMUConversion.accelerationMetersPerSecondSquared(
            timestampNanoseconds: timestamp,
            xInG: data.acceleration.x,
            yInG: data.acceleration.y,
            zInG: data.acceleration.z
        )
        let batch = imuAssemblerLock.withLock { imuAssembler.ingestAcceleration(sample) }
        processIMUAssemblyBatch(batch)
    }

    private func processIMUAssemblyBatch(_ batch: IMUAssemblyBatch) {
        if let violation = batch.violation {
            switch violation {
            case .gyroscopeTimestampRegression,
                 .accelerationTimestampRegression,
                 .outputTimestampRegression:
                accounting.recordTimestampRegression()
            case .pendingGyroscopeOverflow:
                accounting.recordMotionError()
            case .inputSealed:
                accounting.recordMotionError()
            }
            failAndScheduleStop()
            return
        }
        for sample in batch.samples {
            imuHandoff.offer(sample)
        }
    }

    private func registerCaptureNotifications() {
        let center = NotificationCenter.default
        notificationTokens.append(
            center.addObserver(
                forName: AVCaptureSession.wasInterruptedNotification,
                object: captureSession,
                queue: nil
            ) { [weak self] _ in
                guard let self else { return }
                accounting.recordCaptureInterruption()
                lifecycleLock.withLock {
                    if self.lifecycle.state == .running {
                        try? self.lifecycle.transition(to: .interrupted)
                    }
                }
                failAndScheduleStop()
            }
        )
        notificationTokens.append(
            center.addObserver(
                forName: AVCaptureSession.interruptionEndedNotification,
                object: captureSession,
                queue: nil
            ) { [weak self] _ in
                guard let self else { return }
                lifecycleLock.withLock {
                    if self.lifecycle.state == .interrupted {
                        try? self.lifecycle.transition(to: .running)
                    }
                }
            }
        )
        notificationTokens.append(
            center.addObserver(
                forName: AVCaptureSession.runtimeErrorNotification,
                object: captureSession,
                queue: nil
            ) { [weak self] _ in
                guard let self else { return }
                accounting.recordCaptureRuntimeError()
                failAndScheduleStop()
            }
        )
    }

    private func unregisterCaptureNotifications() {
        let center = NotificationCenter.default
        notificationTokens.forEach(center.removeObserver)
        notificationTokens.removeAll(keepingCapacity: false)
    }

    private func transition(to next: SensorTransportLifecycle.State) throws {
        try lifecycleLock.withLock {
            try lifecycle.transition(to: next)
        }
    }

    private func moveToFailedIfPossible() {
        lifecycleLock.withLock {
            switch lifecycle.state {
            case .starting, .running, .interrupted:
                try? lifecycle.transition(to: .failed)
            case .idle, .failed, .stopping, .sealed, .drained:
                break
            }
        }
    }

    private func failAndScheduleStop() {
        moveToFailedIfPossible()
        controlQueue.async { [weak self] in
            self?.stop()
        }
    }

    private func updateDrainedStateIfNeeded() {
        let activeInputsDrained = imuDeliveryMode == .basaltGyroDrivenPaired
            ? cameraHandoff.state == .drained && imuHandoff.state == .drained
            : xrslamSensorHandoff.state == .drained
        guard activeInputsDrained else {
            return
        }
        lifecycleLock.withLock {
            if lifecycle.state == .sealed {
                try? lifecycle.transition(to: .drained)
            }
        }
    }
}

extension LiveSensorTransport: AVCaptureVideoDataOutputSampleBufferDelegate {
    public func captureOutput(
        _ output: AVCaptureOutput,
        didOutput sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        accounting.recordCameraInput()
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer),
              CVPixelBufferGetPixelFormatType(pixelBuffer)
                == kCVPixelFormatType_420YpCbCr8BiPlanarFullRange,
              CVPixelBufferIsPlanar(pixelBuffer),
              CVPixelBufferGetPlaneCount(pixelBuffer) > 0,
              CVPixelBufferGetWidthOfPlane(pixelBuffer, 0) == Int(configuration.cameraWidth),
              CVPixelBufferGetHeightOfPlane(pixelBuffer, 0) == Int(configuration.cameraHeight) else {
            accounting.recordCameraDrop(.invalidFormat)
            return
        }

        // AVCapture timestamps are expressed on the session synchronization
        // clock. Convert explicitly instead of assuming that clock is already
        // the Core Media host clock used by MonotonicClockMapper.
        guard let synchronizationClock = captureSession.synchronizationClock else {
            accounting.recordCameraDrop(.invalidTimestamp)
            failAndScheduleStop()
            return
        }
        let hostTime = CMSyncConvertTime(
            CMSampleBufferGetPresentationTimeStamp(sampleBuffer),
            from: synchronizationClock,
            to: CMClockGetHostTimeClock()
        )
        let hostTimeSeconds = CMTimeGetSeconds(hostTime)
        guard let timestamp = try? clockMapper.cameraNanoseconds(
            hostTimeSeconds: hostTimeSeconds
        ) else {
            accounting.recordCameraDrop(.invalidTimestamp)
            failAndScheduleStop()
            return
        }
        guard cameraTimestamps.observe(timestamp) == .accepted else {
            accounting.recordCameraDrop(.timestampRegression)
            failAndScheduleStop()
            return
        }

        let frame = MonochromeCameraFrame(
            timestampNanoseconds: timestamp,
            pixelBuffer: pixelBuffer,
            width: Int(configuration.cameraWidth),
            height: Int(configuration.cameraHeight)
        )
        if imuDeliveryMode == .xrslamRawSeparateEvents {
            xrslamSensorHandoff.offer(.camera(frame))
        } else {
            cameraHandoff.offer(frame)
        }
        // Strictly after handoff: the preview can never delay admission or change
        // what the engine receives.
        previewTap?.offer(pixelBuffer: pixelBuffer, monotonicNanoseconds: timestamp)
    }

    public func captureOutput(
        _ output: AVCaptureOutput,
        didDrop sampleBuffer: CMSampleBuffer,
        from connection: AVCaptureConnection
    ) {
        accounting.recordCameraDrop(Self.cameraDropReason(for: sampleBuffer))
    }

    private static func cameraDropReason(for sampleBuffer: CMSampleBuffer) -> CameraDropReason {
        guard let reason = CMGetAttachment(
            sampleBuffer,
            key: kCMSampleBufferAttachmentKey_DroppedFrameReason,
            attachmentModeOut: nil
        ) else {
            return .unknown
        }
        if CFEqual(reason, kCMSampleBufferDroppedFrameReason_FrameWasLate) {
            return .late
        }
        if CFEqual(reason, kCMSampleBufferDroppedFrameReason_OutOfBuffers) {
            return .outOfBuffers
        }
        if CFEqual(reason, kCMSampleBufferDroppedFrameReason_Discontinuity) {
            return .discontinuity
        }
        return .unknown
    }
}
