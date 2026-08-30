import CoreVideo
import Foundation

enum XRSLAMNativeSessionError: LocalizedError {
    case status(operation: String, code: xrslam_bench_status_t)
    case invalidTimestamp
    case invalidImageGeometry(expected: String, actual: String)
    case missingLumaPlane

    var errorDescription: String? {
        switch self {
        case .status(let operation, let code):
            return "XRSLAM \(operation) failed: \(String(cString: xrslam_bench_status_name(code)))"
        case .invalidTimestamp:
            return "Sensor timestamp is outside XRSLAM's signed Int64 nanosecond range."
        case .invalidImageGeometry(let expected, let actual):
            return "XRSLAM image geometry mismatch; expected \(expected), received \(actual)."
        case .missingLumaPlane:
            return "Camera frame does not expose a readable 8-bit luma plane."
        }
    }
}

/// Swift ownership layer for the frozen generic XRSLAM core. All estimator
/// calls are made by BenchmarkCoordinator's single run queue. The native bridge
/// preserves accepted sensor callback order; this type adds only buffer
/// ownership, run receipts, and the official BODY_POSE-to-TUM field mapping.
final class XRSLAMNativeSession {
    private var handle: OpaquePointer?
    private let imageWidth: Int
    private let imageHeight: Int
    private var acceptedCameraTimes: [Int64: UInt64] = [:]
    private var trackingPoseResults: UInt64 = 0
    private var initializingResults: UInt64 = 0
    private var trackingFailureResults: UInt64 = 0
    private var degenerateQuaternionResults: UInt64 = 0
    private let stopRequestLock = NSLock()
    private var stopWasRequested = false

    init(
        configURL: URL,
        calibrationURL: URL,
        imageWidth: Int,
        imageHeight: Int
    ) throws {
        guard imageWidth > 0, imageHeight > 0,
              imageWidth <= Int(UInt32.max), imageHeight <= Int(UInt32.max) else {
            throw XRSLAMNativeSessionError.invalidImageGeometry(
                expected: "positive UInt32 dimensions",
                actual: "\(imageWidth)x\(imageHeight)"
            )
        }
        self.imageWidth = imageWidth
        self.imageHeight = imageHeight

        var created: OpaquePointer?
        let status = configURL.path.withCString { configPath in
            calibrationURL.path.withCString { calibrationPath in
                var options = xrslam_bench_create_options_t()
                options.struct_size = MemoryLayout<xrslam_bench_create_options_t>.size
                options.slam_config_path = configPath
                options.device_config_path = calibrationPath
                options.image_width = UInt32(imageWidth)
                options.image_height = UInt32(imageHeight)
                return xrslam_bench_create(&options, &created)
            }
        }
        try Self.requireOK(status, operation: "create")
        guard let created else {
            throw XRSLAMNativeSessionError.status(
                operation: "create-null",
                code: XRSLAM_BENCH_INTERNAL_ERROR
            )
        }
        handle = created
    }

    deinit {
        close()
    }

    func close() {
        guard let handle else { return }
        self.handle = nil
        xrslam_bench_destroy(handle)
    }

    func submitIMU(_ event: RawIMUEvent) throws {
        guard event.timestampNanoseconds <= UInt64(Int64.max) else {
            throw XRSLAMNativeSessionError.invalidTimestamp
        }
        let sample = event.sample
        let timestamp = Int64(event.timestampNanoseconds)
        let status: xrslam_bench_status_t
        switch event {
        case .acceleration:
            status = xrslam_bench_push_accelerometer_g(
                handle, timestamp, sample.x, sample.y, sample.z
            )
        case .gyroscope:
            status = xrslam_bench_push_gyroscope(
                handle, timestamp, sample.x, sample.y, sample.z
            )
        }
        try Self.requireOK(status, operation: "submit_live_imu")
    }

    func submitIMU(_ sample: EuRoCIMUSample) throws {
        for event in XRSLAMReplayIMUAdapter.orderedEvents(sample) {
            switch event {
            case .gyroscope(let gyroscope):
                try Self.requireOK(
                    xrslam_bench_push_gyroscope(
                        handle,
                        sample.timestampNanoseconds,
                        gyroscope.x,
                        gyroscope.y,
                        gyroscope.z
                    ),
                    operation: "submit_replay_gyroscope"
                )
            case .acceleration(let acceleration):
                try Self.requireOK(
                    xrslam_bench_push_acceleration_mps2(
                        handle,
                        sample.timestampNanoseconds,
                        acceleration.x,
                        acceleration.y,
                        acceleration.z
                    ),
                    operation: "submit_replay_acceleration"
                )
            }
        }
    }

    func submitCamera(_ frame: MonochromeCameraFrame, acceptedNanoseconds: UInt64) throws {
        guard frame.timestampNanoseconds <= UInt64(Int64.max) else {
            throw XRSLAMNativeSessionError.invalidTimestamp
        }
        guard frame.width == imageWidth, frame.height == imageHeight else {
            throw XRSLAMNativeSessionError.invalidImageGeometry(
                expected: "\(imageWidth)x\(imageHeight)",
                actual: "\(frame.width)x\(frame.height)"
            )
        }
        CVPixelBufferLockBaseAddress(frame.pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(frame.pixelBuffer, .readOnly) }
        guard CVPixelBufferGetPlaneCount(frame.pixelBuffer) > frame.lumaPlaneIndex,
              let pixels = CVPixelBufferGetBaseAddressOfPlane(
                frame.pixelBuffer,
                frame.lumaPlaneIndex
              )?.assumingMemoryBound(to: UInt8.self) else {
            throw XRSLAMNativeSessionError.missingLumaPlane
        }
        try submitCamera(
            pixels: pixels,
            width: frame.width,
            height: frame.height,
            bytesPerRow: CVPixelBufferGetBytesPerRowOfPlane(
                frame.pixelBuffer,
                frame.lumaPlaneIndex
            ),
            timestampNanoseconds: Int64(frame.timestampNanoseconds),
            acceptedNanoseconds: acceptedNanoseconds
        )
    }

    func submitCamera(
        images: [GrayscaleImage],
        timestampNanoseconds: Int64,
        acceptedNanoseconds: UInt64
    ) throws {
        guard images.count == 1, let image = images.first else {
            throw XRSLAMNativeSessionError.invalidImageGeometry(
                expected: "one \(imageWidth)x\(imageHeight) grayscale image",
                actual: "\(images.count) images"
            )
        }
        guard image.width == imageWidth, image.height == imageHeight else {
            throw XRSLAMNativeSessionError.invalidImageGeometry(
                expected: "\(imageWidth)x\(imageHeight)",
                actual: "\(image.width)x\(image.height)"
            )
        }
        try image.pixels.withUnsafeBytes { rawBuffer in
            guard let pixels = rawBuffer.bindMemory(to: UInt8.self).baseAddress else {
                throw XRSLAMNativeSessionError.missingLumaPlane
            }
            try submitCamera(
                pixels: pixels,
                width: image.width,
                height: image.height,
                bytesPerRow: image.bytesPerRow,
                timestampNanoseconds: timestampNanoseconds,
                acceptedNanoseconds: acceptedNanoseconds
            )
        }
    }

    func submitEuRoCCameraFile(
        _ imageURL: URL,
        timestampNanoseconds: Int64,
        acceptedNanoseconds: UInt64
    ) throws {
        let status = imageURL.path.withCString { path in
            xrslam_bench_push_euroc_image_file(handle, timestampNanoseconds, path)
        }
        try Self.requireOK(status, operation: "submit_official_euroc_camera")
        acceptedCameraTimes[timestampNanoseconds] = acceptedNanoseconds
        let runStatus = xrslam_bench_run_one_frame(handle)
        if runStatus == XRSLAM_BENCH_NONFINITE_OUTPUT {
            acceptedCameraTimes.removeValue(forKey: timestampNanoseconds)
            return
        }
        try Self.requireOK(runStatus, operation: "run_one_frame")
    }

    func pollPose() throws -> NativePoseSample? {
        while true {
            var output = xrslam_bench_frame_result_t()
            let status = xrslam_bench_poll_result(handle, &output)
            if status == XRSLAM_BENCH_NO_OUTPUT || status == XRSLAM_BENCH_END_OF_STREAM {
                return nil
            }
            try Self.requireOK(status, operation: "poll_pose")
            let accepted = acceptedCameraTimes.removeValue(
                forKey: output.input_timestamp_ns
            ) ?? DispatchTime.now().uptimeNanoseconds

            // Frozen XRSLAM state enum: initializing=0, tracking success=1,
            // tracking fail=2. Only successful estimates are benchmark poses.
            switch output.state {
            case 0:
                initializingResults += 1
                continue
            case 1:
                break
            case 2:
                trackingFailureResults += 1
                continue
            default:
                throw XRSLAMNativeSessionError.status(
                    operation: "invalid_tracking_state",
                    code: XRSLAM_BENCH_INTERNAL_ERROR
                )
            }

            guard let pose = XRSLAMPoseAdapter.makeTimedPose(
                timestampNanoseconds: output.pose_timestamp_ns,
                translationX: output.translation_xyz.0,
                translationY: output.translation_xyz.1,
                translationZ: output.translation_xyz.2,
                quaternionX: output.quaternion_xyzw.0,
                quaternionY: output.quaternion_xyzw.1,
                quaternionZ: output.quaternion_xyzw.2,
                quaternionW: output.quaternion_xyzw.3
            ) else {
                degenerateQuaternionResults += 1
                continue
            }
            trackingPoseResults += 1
            let now = DispatchTime.now().uptimeNanoseconds
            return NativePoseSample(
                pose: pose,
                capturedMonotonicNanoseconds: accepted,
                pipelineLatencyNanoseconds: now >= accepted ? now - accepted : 0
            )
        }
    }

    func snapshot() throws -> VIOEngineSnapshot {
        var native = xrslam_bench_snapshot_t()
        try Self.requireOK(
            xrslam_bench_get_snapshot(handle, &native),
            operation: "snapshot"
        )
        let value = native.counters
        var snapshot = VIOEngineSnapshot()
        snapshot.counters = VIOEngineCounters(
            cameraOffered: value.images_offered,
            cameraAccepted: value.images_accepted,
            cameraDroppedQueueFull: value.images_rejected_queue_full,
            cameraRejectedTimestamp: value.images_rejected_timestamp,
            cameraRejectedSealed: value.images_rejected_sealed,
            cameraBytesCopied: value.image_bytes_copied,
            imuOffered: min(value.accel_offered, value.gyro_offered),
            imuAccepted: min(value.accel_accepted, value.gyro_accepted),
            imuDroppedQueueFull:
                value.accel_rejected_queue_full + value.gyro_rejected_queue_full,
            imuRejectedTimestamp:
                value.accel_rejected_timestamp + value.gyro_rejected_timestamp,
            imuRejectedSealed:
                value.accel_rejected_sealed + value.gyro_rejected_sealed,
            posesProduced: trackingPoseResults,
            posesPolled: trackingPoseResults,
            posesDroppedBridgeQueue: value.results_rejected_queue_full,
            nonfinitePoseRejected:
                value.nonfinite_results_rejected + degenerateQuaternionResults
        )
        snapshot.cameraInputQueue = VIOEngineQueueMeasurement(
            size: native.pending_event_count,
            capacity: native.event_queue_capacity,
            peak: native.event_queue_peak
        )
        snapshot.imuInputQueue = VIOEngineQueueMeasurement(
            size: native.pending_event_count,
            capacity: 0,
            peak: 0
        )
        snapshot.poseBridgeQueuePeak = native.result_queue_peak
        snapshot.additionalCounters = [
            "xrslam_events_offered": value.events_offered,
            "xrslam_events_accepted": value.events_accepted,
            "xrslam_events_processed": value.events_processed,
            "xrslam_events_rejected_queue_full": value.events_rejected_queue_full,
            "xrslam_accel_offered": value.accel_offered,
            "xrslam_accel_accepted": value.accel_accepted,
            "xrslam_accel_processed": value.accel_processed,
            "xrslam_accel_rejected_queue_full": value.accel_rejected_queue_full,
            "xrslam_gyro_offered": value.gyro_offered,
            "xrslam_gyro_accepted": value.gyro_accepted,
            "xrslam_gyro_processed": value.gyro_processed,
            "xrslam_gyro_rejected_queue_full": value.gyro_rejected_queue_full,
            "xrslam_images_offered": value.images_offered,
            "xrslam_images_accepted": value.images_accepted,
            "xrslam_images_processed": value.images_processed,
            "xrslam_images_rejected_queue_full": value.images_rejected_queue_full,
            "xrslam_replay_images_decoded": value.replay_images_decoded,
            "xrslam_replay_images_undistorted": value.replay_images_undistorted,
            "xrslam_replay_image_decode_failures": value.replay_image_decode_failures,
            "xrslam_replay_image_preprocess_failures": value.replay_image_preprocess_failures,
            "xrslam_frames_run": value.frames_run,
            "xrslam_results_produced": value.results_produced,
            "xrslam_results_polled": value.results_polled,
            "xrslam_results_rejected_queue_full": value.results_rejected_queue_full,
            "xrslam_initializing_results": initializingResults,
            "xrslam_tracking_failure_results": trackingFailureResults,
            "xrslam_degenerate_quaternion_results": degenerateQuaternionResults,
            "xrslam_upstream_destroy_calls": value.upstream_destroy_calls,
        ]
        snapshot.effectiveConfiguration = [
            "thread_policy": "single_serial_benchmark_coordinator",
            "sensor_fifo_policy": "serialized_direct_imu_then_image_run",
            "native_image_slot": "one_create_time_preallocated_grayscale_buffer",
            "native_event_queue_capacity": String(native.event_queue_capacity),
            "native_result_queue_capacity": String(native.result_queue_capacity),
            "camera_width": String(imageWidth),
            "camera_height": String(imageHeight),
            "pose_frame": "upstream_body_imu_pose_direct_to_tum",
            "scene_kit_axis_remap_applied": "false",
            "acceleration_live_units_at_bridge": "core_motion_g_times_negative_9_80665",
            "acceleration_replay_units_at_bridge": "meters_per_second_squared_passthrough",
            "replay_equal_timestamp_imu_order": "gyroscope_then_accelerometer",
            "replay_image_decode": "opencv_4_0_1_imread_unchanged",
            "replay_image_undistortion": "opencv_4_0_1_cv_undistort_mh01_cam0_float_kd",
            "config_transport": "filesystem_paths_yaml_load_file",
            "stop_requested": String(stopRequestLock.withLock { stopWasRequested }),
        ]
        return snapshot
    }

    func sealDrainStop() throws {
        try Self.requireOK(xrslam_bench_seal_inputs(handle), operation: "seal")
        try Self.requireOK(xrslam_bench_drain(handle), operation: "drain")
        try Self.requireOK(xrslam_bench_stop(handle), operation: "stop")
    }

    func requestStop() {
        // The frozen core is synchronous and the coordinator is its sole
        // caller. Cross-thread Destroy would violate that contract; the run
        // loop observes this request, then deinit performs seal/drain/stop on
        // the owner queue.
        stopRequestLock.withLock { stopWasRequested = true }
    }

    private func submitCamera(
        pixels: UnsafePointer<UInt8>,
        width: Int,
        height: Int,
        bytesPerRow: Int,
        timestampNanoseconds: Int64,
        acceptedNanoseconds: UInt64
    ) throws {
        var image = xrslam_bench_image_t()
        image.gray_pixels = pixels
        image.width = UInt32(width)
        image.height = UInt32(height)
        image.bytes_per_row = UInt32(bytesPerRow)
        try Self.requireOK(
            xrslam_bench_push_image(handle, timestampNanoseconds, &image),
            operation: "submit_camera"
        )
        acceptedCameraTimes[timestampNanoseconds] = acceptedNanoseconds
        let runStatus = xrslam_bench_run_one_frame(handle)
        if runStatus == XRSLAM_BENCH_NONFINITE_OUTPUT {
            acceptedCameraTimes.removeValue(forKey: timestampNanoseconds)
            return
        }
        try Self.requireOK(runStatus, operation: "run_one_frame")
    }

    private static func requireOK(
        _ status: xrslam_bench_status_t,
        operation: String
    ) throws {
        guard status == XRSLAM_BENCH_OK else {
            throw XRSLAMNativeSessionError.status(operation: operation, code: status)
        }
    }
}
