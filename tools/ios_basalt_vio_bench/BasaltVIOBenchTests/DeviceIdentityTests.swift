import XCTest
@testable import VIOReplacementBench

final class DeviceIdentityTests: XCTestCase {
    func testFrozenIPhone14ProCalibrationIsAccepted() {
        XCTAssertNil(
            LiveCalibrationGate.rejectionReason(
                for: DeviceIdentity(modelIdentifier: "iPhone15,2")
            )
        )
    }

    func testDifferentDeviceCannotSilentlyUseFrozenCalibration() {
        let reason = LiveCalibrationGate.rejectionReason(
            for: DeviceIdentity(modelIdentifier: "iPhone15,3")
        )
        XCTAssertNotNil(reason)
        XCTAssertTrue(reason?.contains("iPhone15,3") == true)
    }
}
