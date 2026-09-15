import XCTest
@testable import VIOReplacementBench

final class ReplayContractGateTests: XCTestCase {
    func testAcceptsCheckedEuRoCCam0MonoIdentities() throws {
        for name in ["EuRoC_MH_01_easy", "EuRoC_V1_01_easy", "EuRoC_V1_02_medium", "EuRoC_V1_03_difficult"] {
            XCTAssertNoThrow(
                try ReplayContractGate.validate(datasetName: name, inputCameraCount: 1),
                "\(name) is a checked identity and must pass"
            )
        }
        XCTAssertThrowsError(
            try ReplayContractGate.validate(datasetName: "synthetic_euroc", inputCameraCount: 1)
        )
        XCTAssertThrowsError(
            try ReplayContractGate.validate(datasetName: "EuRoC_V1_01_easy_gtspan", inputCameraCount: 1)
        )
        XCTAssertThrowsError(
            try ReplayContractGate.validate(datasetName: "EuRoC_MH_01_easy", inputCameraCount: 2)
        )
    }
}
