import XCTest
@testable import VIOReplacementBench

final class ReplayContractGateTests: XCTestCase {
    func testAcceptsOnlyFrozenMH01Cam0MonoIdentity() throws {
        XCTAssertNoThrow(
            try ReplayContractGate.validate(
                datasetName: "EuRoC_MH_01_easy",
                inputCameraCount: 1
            )
        )
        XCTAssertThrowsError(
            try ReplayContractGate.validate(datasetName: "synthetic_euroc", inputCameraCount: 1)
        )
        XCTAssertThrowsError(
            try ReplayContractGate.validate(datasetName: "EuRoC_MH_01_easy", inputCameraCount: 2)
        )
    }
}
