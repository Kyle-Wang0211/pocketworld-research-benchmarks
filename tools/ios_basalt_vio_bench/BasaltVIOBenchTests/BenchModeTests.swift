import XCTest
@testable import VIOReplacementBench

final class BenchModeTests: XCTestCase {
    func testOnlyApprovedModesExist() {
        XCTAssertEqual(BenchMode.allCases.map(\.rawValue), [
            "live-soak", "replay-paced", "replay-max"
        ])
    }

    func testNativeBackendFailsClosedUntilRealCoreIsLinked() {
        #if PW_BASALT_CORE_LINKED
        XCTAssertEqual(basalt_bench_backend_available(), 1)
        #else
        XCTAssertEqual(basalt_bench_backend_available(), 0)
        #endif
    }
}

