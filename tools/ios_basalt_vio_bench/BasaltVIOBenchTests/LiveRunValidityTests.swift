import XCTest
@testable import VIOReplacementBench

final class LiveRunValidityTests: XCTestCase {
    func testAcceptsZeroLossTransport() {
        XCTAssertNil(LiveRunValidity.invalidReason(.zero))
    }

    func testEveryIMUOrPoseLossInvalidatesRun() {
        let cases: [(LiveRunLossCounters, String)] = [
            (.zero.replacing(motionErrors: 1), "motion_transport_error"),
            (.zero.replacing(platformCameraDrops: 1), "platform_camera_loss"),
            (.zero.replacing(captureInterruptions: 1), "capture_interruption"),
            (.zero.replacing(captureRuntimeErrors: 1), "capture_runtime_error"),
            (.zero.replacing(timestampRegressions: 1), "timestamp_regression"),
            (.zero.replacing(applicationLifecycleViolations: 1), "app_backgrounded"),
            (.zero.replacing(imuAssemblyDrops: 1), "imu_assembly_loss"),
            (.zero.replacing(cameraHandoffDrops: 1), "camera_handoff_loss"),
            (.zero.replacing(combinedSensorHandoffDrops: 1), "combined_sensor_handoff_loss"),
            (.zero.replacing(imuHandoffDrops: 1), "imu_handoff_loss"),
            (.zero.replacing(nativeIMUDrops: 1), "native_imu_transport_loss"),
            (.zero.replacing(nativeIMURejections: 1), "native_imu_rejection"),
            (.zero.replacing(nativeCameraTransportLoss: 1), "native_camera_transport_loss"),
            (.zero.replacing(nativeCameraTimestampRejections: 1), "native_camera_timestamp_rejection"),
            (.zero.replacing(poseBridgeDrops: 1), "pose_bridge_loss"),
            (.zero.replacing(nonfinitePoses: 1), "non_finite_pose"),
        ]
        for (counters, expected) in cases {
            XCTAssertEqual(LiveRunValidity.invalidReason(counters), expected)
        }
    }

    func testARKitFinalValidityCoversFullMeasurementAndDrain() {
        XCTAssertNil(
            ARKitRunValidity.invalidReason(
                snapshot: ARKitReferenceSnapshot(),
                applicationLifecycleViolations: 0
            )
        )

        var interrupted = ARKitReferenceSnapshot()
        interrupted.sessionInterruptions = 1
        XCTAssertEqual(
            ARKitRunValidity.invalidReason(
                snapshot: interrupted,
                applicationLifecycleViolations: 0
            ),
            "arkit_session_interruption"
        )

        var failed = ARKitReferenceSnapshot()
        failed.sessionFailures = 1
        XCTAssertEqual(
            ARKitRunValidity.invalidReason(
                snapshot: failed,
                applicationLifecycleViolations: 0
            ),
            "arkit_session_failure"
        )

        var regressed = ARKitReferenceSnapshot()
        regressed.timestampRegressions = 1
        XCTAssertEqual(
            ARKitRunValidity.invalidReason(
                snapshot: regressed,
                applicationLifecycleViolations: 0
            ),
            "arkit_timestamp_regression"
        )

        var nonfinite = ARKitReferenceSnapshot()
        nonfinite.nonfinitePoses = 1
        XCTAssertEqual(
            ARKitRunValidity.invalidReason(
                snapshot: nonfinite,
                applicationLifecycleViolations: 0
            ),
            "non_finite_pose"
        )

        var callbackAfterPause = ARKitReferenceSnapshot()
        callbackAfterPause.callbacksAfterPause = 1
        XCTAssertEqual(
            ARKitRunValidity.invalidReason(
                snapshot: callbackAfterPause,
                applicationLifecycleViolations: 0
            ),
            "arkit_callbacks_after_pause"
        )

        XCTAssertEqual(
            ARKitRunValidity.invalidReason(
                snapshot: ARKitReferenceSnapshot(),
                applicationLifecycleViolations: 1
            ),
            "app_backgrounded"
        )
    }
}
