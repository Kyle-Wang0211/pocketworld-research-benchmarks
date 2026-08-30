import Foundation
import XCTest
@testable import VIOReplacementBench

final class CalibrationMaterializerTests: XCTestCase {
    func testCam0SlicePreservesFirstCameraAndAllNonCameraFields() throws {
        let source: [String: Any] = [
            "value0": [
                "T_imu_cam": [["px": 1], ["px": 2]],
                "intrinsics": [["camera": 0], ["camera": 1]],
                "resolution": [[752, 480], [752, 480]],
                "vignette": [["camera": 0], ["camera": 1]],
                "gyro_noise_std": [1, 2, 3],
            ]
        ]
        let data = try JSONSerialization.data(withJSONObject: source)
        let result = try CalibrationMaterializer.eurocCam0Only(from: data)
        let root = try XCTUnwrap(
            JSONSerialization.jsonObject(with: result) as? [String: Any]
        )
        let value = try XCTUnwrap(root["value0"] as? [String: Any])

        XCTAssertEqual((value["T_imu_cam"] as? [[String: Int]])?.count, 1)
        XCTAssertEqual((value["T_imu_cam"] as? [[String: Int]])?.first?["px"], 1)
        XCTAssertEqual(value["gyro_noise_std"] as? [Int], [1, 2, 3])
    }

    func testRejectsAlreadyMonoInputInsteadOfSilentlyChangingContract() throws {
        let source: [String: Any] = [
            "value0": [
                "T_imu_cam": [["px": 1]],
                "intrinsics": [["camera": 0]],
                "resolution": [[752, 480]],
                "vignette": [["camera": 0]],
            ]
        ]
        let data = try JSONSerialization.data(withJSONObject: source)
        XCTAssertThrowsError(try CalibrationMaterializer.eurocCam0Only(from: data)) {
            XCTAssertEqual(
                $0 as? CalibrationMaterializerError,
                .insufficientCameraEntries("T_imu_cam")
            )
        }
    }
}
