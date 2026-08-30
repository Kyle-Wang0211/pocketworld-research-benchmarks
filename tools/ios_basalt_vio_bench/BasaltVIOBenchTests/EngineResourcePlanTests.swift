import XCTest
@testable import VIOReplacementBench

final class EngineResourcePlanTests: XCTestCase {
    func testBasaltAndXRSLAMUseTheirOwnPinnedConfigurationFamilies() {
        XCTAssertEqual(
            EngineResourcePlan.forRun(backend: .basalt, mode: .liveSoak),
            EngineResourcePlan(config: "euroc_config.json", calibration: "iphone_14_pro_640x480_calib.json")
        )
        XCTAssertEqual(
            EngineResourcePlan.forRun(backend: .xrslam, mode: .liveSoak),
            EngineResourcePlan(config: "xrslam_ios_vio.yaml", calibration: "xrslam_iphone_14_pro.yaml")
        )
        XCTAssertEqual(
            EngineResourcePlan.forRun(backend: .xrslam, mode: .replayPaced),
            EngineResourcePlan(config: "xrslam_euroc_vio.yaml", calibration: "xrslam_euroc_sensor.yaml")
        )
        XCTAssertEqual(
            EngineResourcePlan.forRun(backend: .arkit, mode: .liveSoak),
            EngineResourcePlan(
                config: "arkit_production_reference.json",
                calibration: "arkit_runtime_calibration.json"
            )
        )
    }
}
