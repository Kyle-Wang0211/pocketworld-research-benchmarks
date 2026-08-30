import XCTest
@testable import VIOReplacementBench

final class ARKitReferenceAccountingTests: XCTestCase {
    private let pose = TimedPose(
        timestampNanoseconds: 1_000_000_000,
        translation: Vector3(x: 0, y: 0, z: 0),
        rotation: .identity
    )

    func testFramesRecordTrackingMappingLatencyAndFirstNormal() {
        let accounting = ARKitReferenceAccounting(
            startMonotonicSeconds: 10,
            nominalFramesPerSecond: 30
        )
        accounting.recordFrame(
            timestampSeconds: 10.000,
            callbackSeconds: 10.010,
            pose: pose,
            tracking: .limitedInitializing,
            mapping: .limited
        )
        accounting.recordFrame(
            timestampSeconds: 10.033,
            callbackSeconds: 10.041,
            pose: TimedPose(
                timestampNanoseconds: 10_033_000_000,
                translation: Vector3(x: 0.01, y: 0, z: 0),
                rotation: .identity
            ),
            tracking: .normal,
            mapping: .extending
        )

        let snapshot = accounting.snapshot()
        XCTAssertEqual(snapshot.framesReceived, 2)
        XCTAssertEqual(snapshot.finitePoses, 2)
        XCTAssertEqual(snapshot.trackingLimitedInitializing, 1)
        XCTAssertEqual(snapshot.trackingNormal, 1)
        XCTAssertEqual(snapshot.mappingLimited, 1)
        XCTAssertEqual(snapshot.mappingExtending, 1)
        XCTAssertEqual(snapshot.firstNormalLatencyMilliseconds!, 33, accuracy: 0.001)
        XCTAssertEqual(
            snapshot.firstNormalDeliveryLatencyMilliseconds!,
            41,
            accuracy: 0.001
        )
        XCTAssertNil(snapshot.firstMappedLatencyMilliseconds)
        XCTAssertEqual(snapshot.trackingTransitions, 1)
        XCTAssertEqual(snapshot.mappingTransitions, 1)
        XCTAssertEqual(snapshot.frameIntervalsMilliseconds[0], 33, accuracy: 0.001)
        XCTAssertEqual(snapshot.callbackLatenciesMilliseconds.count, 2)
        XCTAssertEqual(snapshot.callbackLatenciesMilliseconds[0], 10, accuracy: 0.001)
        XCTAssertEqual(snapshot.callbackLatenciesMilliseconds[1], 8, accuracy: 0.001)
        XCTAssertEqual(snapshot.estimatedMissedFrames, 0)
    }

    func testTimestampRegressionAndGapAreExplicitlyAccounted() {
        let accounting = ARKitReferenceAccounting(
            startMonotonicSeconds: 1,
            nominalFramesPerSecond: 30
        )
        accounting.recordFrame(
            timestampSeconds: 1.000,
            callbackSeconds: 1.005,
            pose: pose,
            tracking: .normal,
            mapping: .mapped
        )
        accounting.recordFrame(
            timestampSeconds: 1.100,
            callbackSeconds: 1.106,
            pose: pose,
            tracking: .limitedRelocalizing,
            mapping: .limited
        )
        accounting.recordFrame(
            timestampSeconds: 1.050,
            callbackSeconds: 1.110,
            pose: pose,
            tracking: .notAvailable,
            mapping: .notAvailable
        )

        let snapshot = accounting.snapshot()
        XCTAssertEqual(snapshot.estimatedMissedFrames, 2)
        XCTAssertEqual(snapshot.stallEventsOverOneSecond, 0)
        XCTAssertEqual(snapshot.timestampRegressions, 1)
        XCTAssertEqual(snapshot.trackingLimitedRelocalizing, 1)
        XCTAssertEqual(snapshot.trackingNotAvailable, 1)
    }

    func testInvalidPoseLatencyInterruptionFailureAndPostPauseCallbacksFailClosed() {
        let accounting = ARKitReferenceAccounting(
            startMonotonicSeconds: 5,
            nominalFramesPerSecond: 30
        )
        accounting.recordInterruption()
        accounting.recordFailure()
        accounting.recordFrame(
            timestampSeconds: 5.0,
            callbackSeconds: 4.9,
            pose: TimedPose(
                timestampNanoseconds: 5_000_000_000,
                translation: Vector3(x: .nan, y: 0, z: 0),
                rotation: .identity
            ),
            tracking: .normal,
            mapping: .mapped
        )
        accounting.markPaused(timestampSeconds: 1_000_000)
        accounting.recordFrame(
            timestampSeconds: 5.033,
            callbackSeconds: 5.040,
            pose: pose,
            tracking: .normal,
            mapping: .mapped
        )

        let snapshot = accounting.snapshot()
        XCTAssertEqual(snapshot.sessionInterruptions, 1)
        XCTAssertEqual(snapshot.sessionFailures, 1)
        XCTAssertEqual(snapshot.nonfinitePoses, 1)
        XCTAssertEqual(snapshot.invalidCallbackLatencies, 1)
        XCTAssertEqual(snapshot.callbacksAfterPause, 1)
        XCTAssertEqual(snapshot.framesReceived, 1)
    }

    func testStallDwellMappingAndRelocalizationRecoveryAreMeasured() {
        let accounting = ARKitReferenceAccounting(
            startMonotonicSeconds: 20,
            nominalFramesPerSecond: 30
        )
        accounting.recordFrame(
            timestampSeconds: 20,
            callbackSeconds: 20.01,
            pose: pose,
            tracking: .limitedRelocalizing,
            mapping: .limited
        )
        accounting.recordFrame(
            timestampSeconds: 21.2,
            callbackSeconds: 21.21,
            pose: pose,
            tracking: .normal,
            mapping: .mapped
        )
        accounting.recordHandlerDuration(milliseconds: 2.5)

        let snapshot = accounting.snapshot()
        XCTAssertEqual(snapshot.stallEventsOverOneSecond, 1)
        XCTAssertEqual(snapshot.stallDurationMilliseconds, 1_200, accuracy: 0.001)
        XCTAssertEqual(snapshot.relocalizationAttempts, 1)
        XCTAssertEqual(snapshot.relocalizationRecoveries, 1)
        XCTAssertEqual(snapshot.relocalizationRecoveryMilliseconds.count, 1)
        XCTAssertEqual(
            snapshot.relocalizationRecoveryMilliseconds[0],
            1_200,
            accuracy: 0.001
        )
        XCTAssertEqual(snapshot.firstMappedLatencyMilliseconds!, 1_200, accuracy: 0.001)
        XCTAssertEqual(snapshot.trackingDwellSeconds["limited_relocalizing"]!, 1.2, accuracy: 0.001)
        XCTAssertEqual(snapshot.mappingDwellSeconds["limited"]!, 1.2, accuracy: 0.001)
        XCTAssertEqual(snapshot.callbackHandlerDurationsMilliseconds, [2.5])
    }
}

extension ARKitReferenceAccountingTests {
    private static func flatPose(at seconds: Double) -> TimedPose {
        TimedPose(
            timestampNanoseconds: Int64((seconds * 1_000_000_000).rounded()),
            translation: Vector3(x: 0, y: 0, z: 0),
            rotation: .identity
        )
    }

    /// A frame captured before the stop but delivered after it is ARKit's normal
    /// queueing behaviour, not evidence the session outlived the pause. Counting
    /// it as a post-pause callback invalidated a clean 30 s recording.
    func testLateDeliveryOfPreStopFrameDoesNotInvalidateTheRun() {
        let accounting = ARKitReferenceAccounting(
            startMonotonicSeconds: 10, nominalFramesPerSecond: 60
        )
        accounting.recordFrame(
            timestampSeconds: 10.0, callbackSeconds: 10.0,
            pose: Self.flatPose(at: 10.0),
            tracking: .normal, mapping: .mapped
        )
        accounting.markPaused(timestampSeconds: 10.5)

        // Captured before the stop, delivered after it.
        accounting.recordFrame(
            timestampSeconds: 10.4, callbackSeconds: 10.6,
            pose: Self.flatPose(at: 10.4),
            tracking: .normal, mapping: .mapped
        )
        let late = accounting.statusSnapshot()
        XCTAssertEqual(late.lateFrameDeliveries, 1)
        XCTAssertEqual(late.callbacksAfterPause, 0)

        // Captured after the stop: the session really did keep running.
        accounting.recordFrame(
            timestampSeconds: 10.9, callbackSeconds: 11.0,
            pose: Self.flatPose(at: 10.9),
            tracking: .normal, mapping: .mapped
        )
        XCTAssertEqual(accounting.statusSnapshot().callbacksAfterPause, 1)
    }
}
