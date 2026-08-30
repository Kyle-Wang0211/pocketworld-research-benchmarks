import XCTest
@testable import VIOReplacementBench

final class BenchBackendTests: XCTestCase {
    func testBasaltBuildIdentityIsFrozenAndNotProduction() {
        let backend = BenchBackend.basalt
        XCTAssertEqual(backend.id, "basalt")
        XCTAssertEqual(backend.upstreamRevision, "0f3b2b52c807f70ff4e2973ce253c73329eea7bc")
        XCTAssertEqual(backend.bundleID, "com.kyle.viobench")
        XCTAssertNotEqual(backend.bundleID, "com.kyle.PocketWorld")
        // Asserted against the bundled contract rather than a literal: pinning
        // the literal here is what let the contract move to v2 while every
        // receipt kept declaring v1, with the test still green.
        XCTAssertEqual(backend.experimentID, BenchExperimentIdentity.experimentID)
        XCTAssertTrue(
            BenchExperimentIdentity.isAvailable,
            "contract.json must be bundled; without it every receipt fails validation"
        )
        XCTAssertFalse(backend.usesARKit)
    }

    func testOneAppUsesThreeImmutableEngineIdentities() {
        XCTAssertEqual(BenchBackend.basalt.bundleID, BenchBackend.xrslam.bundleID)
        XCTAssertEqual(BenchBackend.xrslam.bundleID, BenchBackend.arkit.bundleID)
        XCTAssertNotEqual(BenchBackend.basalt.openCVVersion, BenchBackend.xrslam.openCVVersion)
        XCTAssertEqual(BenchBackend.xrslam.upstreamRevision, "4beb1a942f33da9afbfae2d70e2c641cfc2bb675")
        XCTAssertTrue(BenchBackend.arkit.usesARKit)
        XCTAssertEqual(Set(BenchBackend.allCases.map(\.id)).count, 3)
    }
}
