import XCTest
@testable import VIOReplacementBench

final class XRSLAMPoseAdapterTests: XCTestCase {
    func testBodyPoseMapsDirectlyToWorldFromIMUWithoutDisplayAxisSwap() throws {
        let pose = try XCTUnwrap(XRSLAMPoseAdapter.makeTimedPose(
            timestampNanoseconds: 123,
            translationX: 1,
            translationY: 2,
            translationZ: 3,
            quaternionX: 0.1,
            quaternionY: 0.2,
            quaternionZ: 0.3,
            quaternionW: 0.9
        ))

        XCTAssertEqual(pose.timestampNanoseconds, 123)
        XCTAssertEqual(pose.translation, Vector3(x: 1, y: 2, z: 3))
        let norm = sqrt(0.1 * 0.1 + 0.2 * 0.2 + 0.3 * 0.3 + 0.9 * 0.9)
        XCTAssertEqual(pose.rotation.x, 0.1 / norm, accuracy: 1e-12)
        XCTAssertEqual(pose.rotation.y, 0.2 / norm, accuracy: 1e-12)
        XCTAssertEqual(pose.rotation.z, 0.3 / norm, accuracy: 1e-12)
        XCTAssertEqual(pose.rotation.w, 0.9 / norm, accuracy: 1e-12)
    }

    func testDegenerateQuaternionIsRejected() {
        XCTAssertNil(XRSLAMPoseAdapter.makeTimedPose(
            timestampNanoseconds: 1,
            translationX: 0,
            translationY: 0,
            translationZ: 0,
            quaternionX: 0,
            quaternionY: 0,
            quaternionZ: 0,
            quaternionW: 0
        ))
    }

    func testReplayIMUOrderMatchesPinnedOfficialEuRoCReader() {
        let sample = EuRoCIMUSample(
            timestampNanoseconds: 123,
            gyroscopeRadiansPerSecond: Vector3(x: 1, y: 2, z: 3),
            accelerationMetersPerSecondSquared: Vector3(x: 4, y: 5, z: 6)
        )

        XCTAssertEqual(XRSLAMReplayIMUAdapter.orderedEvents(sample), [
            .gyroscope(MotionVectorSample(
                timestampNanoseconds: 123, x: 1, y: 2, z: 3
            )),
            .acceleration(MotionVectorSample(
                timestampNanoseconds: 123, x: 4, y: 5, z: 6
            )),
        ])
    }
}
