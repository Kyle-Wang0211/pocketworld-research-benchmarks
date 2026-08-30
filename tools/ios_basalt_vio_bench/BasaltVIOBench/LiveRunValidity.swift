import Foundation

struct LiveRunLossCounters: Equatable {
    let motionErrors: UInt64
    let platformCameraDrops: UInt64
    let captureInterruptions: UInt64
    let captureRuntimeErrors: UInt64
    let timestampRegressions: UInt64
    let applicationLifecycleViolations: UInt64
    let imuAssemblyDrops: UInt64
    let cameraHandoffDrops: UInt64
    let combinedSensorHandoffDrops: UInt64
    let imuHandoffDrops: UInt64
    let nativeIMUDrops: UInt64
    let nativeIMURejections: UInt64
    let nativeCameraTransportLoss: UInt64
    let nativeCameraTimestampRejections: UInt64
    let poseBridgeDrops: UInt64
    let nonfinitePoses: UInt64

    static let zero = LiveRunLossCounters(
        motionErrors: 0,
        platformCameraDrops: 0,
        captureInterruptions: 0,
        captureRuntimeErrors: 0,
        timestampRegressions: 0,
        applicationLifecycleViolations: 0,
        imuAssemblyDrops: 0,
        cameraHandoffDrops: 0,
        combinedSensorHandoffDrops: 0,
        imuHandoffDrops: 0,
        nativeIMUDrops: 0,
        nativeIMURejections: 0,
        nativeCameraTransportLoss: 0,
        nativeCameraTimestampRejections: 0,
        poseBridgeDrops: 0,
        nonfinitePoses: 0
    )

    func replacing(
        motionErrors: UInt64? = nil,
        platformCameraDrops: UInt64? = nil,
        captureInterruptions: UInt64? = nil,
        captureRuntimeErrors: UInt64? = nil,
        timestampRegressions: UInt64? = nil,
        applicationLifecycleViolations: UInt64? = nil,
        imuAssemblyDrops: UInt64? = nil,
        cameraHandoffDrops: UInt64? = nil,
        combinedSensorHandoffDrops: UInt64? = nil,
        imuHandoffDrops: UInt64? = nil,
        nativeIMUDrops: UInt64? = nil,
        nativeIMURejections: UInt64? = nil,
        nativeCameraTransportLoss: UInt64? = nil,
        nativeCameraTimestampRejections: UInt64? = nil,
        poseBridgeDrops: UInt64? = nil,
        nonfinitePoses: UInt64? = nil
    ) -> LiveRunLossCounters {
        LiveRunLossCounters(
            motionErrors: motionErrors ?? self.motionErrors,
            platformCameraDrops: platformCameraDrops ?? self.platformCameraDrops,
            captureInterruptions: captureInterruptions ?? self.captureInterruptions,
            captureRuntimeErrors: captureRuntimeErrors ?? self.captureRuntimeErrors,
            timestampRegressions: timestampRegressions ?? self.timestampRegressions,
            applicationLifecycleViolations:
                applicationLifecycleViolations ?? self.applicationLifecycleViolations,
            imuAssemblyDrops: imuAssemblyDrops ?? self.imuAssemblyDrops,
            cameraHandoffDrops: cameraHandoffDrops ?? self.cameraHandoffDrops,
            combinedSensorHandoffDrops:
                combinedSensorHandoffDrops ?? self.combinedSensorHandoffDrops,
            imuHandoffDrops: imuHandoffDrops ?? self.imuHandoffDrops,
            nativeIMUDrops: nativeIMUDrops ?? self.nativeIMUDrops,
            nativeIMURejections: nativeIMURejections ?? self.nativeIMURejections,
            nativeCameraTransportLoss:
                nativeCameraTransportLoss ?? self.nativeCameraTransportLoss,
            nativeCameraTimestampRejections: nativeCameraTimestampRejections ?? self.nativeCameraTimestampRejections,
            poseBridgeDrops: poseBridgeDrops ?? self.poseBridgeDrops,
            nonfinitePoses: nonfinitePoses ?? self.nonfinitePoses
        )
    }
}

enum LiveRunValidity {
    static func invalidReason(_ counters: LiveRunLossCounters) -> String? {
        if counters.motionErrors > 0 { return "motion_transport_error" }
        if counters.platformCameraDrops > 0 { return "platform_camera_loss" }
        if counters.captureInterruptions > 0 { return "capture_interruption" }
        if counters.captureRuntimeErrors > 0 { return "capture_runtime_error" }
        if counters.timestampRegressions > 0 { return "timestamp_regression" }
        if counters.applicationLifecycleViolations > 0 { return "app_backgrounded" }
        if counters.imuAssemblyDrops > 0 { return "imu_assembly_loss" }
        if counters.cameraHandoffDrops > 0 { return "camera_handoff_loss" }
        if counters.combinedSensorHandoffDrops > 0 {
            return "combined_sensor_handoff_loss"
        }
        if counters.imuHandoffDrops > 0 { return "imu_handoff_loss" }
        if counters.nativeIMUDrops > 0 { return "native_imu_transport_loss" }
        if counters.nativeIMURejections > 0 { return "native_imu_rejection" }
        if counters.nativeCameraTransportLoss > 0 {
            return "native_camera_transport_loss"
        }
        if counters.nativeCameraTimestampRejections > 0 {
            return "native_camera_timestamp_rejection"
        }
        if counters.poseBridgeDrops > 0 { return "pose_bridge_loss" }
        if counters.nonfinitePoses > 0 { return "non_finite_pose" }
        return nil
    }
}

enum ARKitRunValidity {
    static func invalidReason(
        snapshot: ARKitReferenceSnapshot,
        applicationLifecycleViolations: UInt64
    ) -> String? {
        if applicationLifecycleViolations > 0 { return "app_backgrounded" }
        if snapshot.sessionInterruptions > 0 { return "arkit_session_interruption" }
        if snapshot.sessionFailures > 0 { return "arkit_session_failure" }
        if snapshot.timestampRegressions > 0 { return "arkit_timestamp_regression" }
        if snapshot.nonfinitePoses > 0 { return "non_finite_pose" }
        if snapshot.callbacksAfterPause > 0 { return "arkit_callbacks_after_pause" }
        return nil
    }
}
