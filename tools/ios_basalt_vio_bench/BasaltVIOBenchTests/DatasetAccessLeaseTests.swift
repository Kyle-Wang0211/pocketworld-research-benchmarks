import Foundation
import XCTest
@testable import VIOReplacementBench

final class DatasetAccessLeaseTests: XCTestCase {
    func testContainerDatasetDoesNotRequestSecurityScope() throws {
        var starts = 0
        var stops = 0
        let container = URL(fileURLWithPath: "/private/var/mobile/Containers/Data/Application/abc")
        let dataset = container.appendingPathComponent("Documents/MH_01_easy")

        let lease = try DatasetAccessLease.acquire(
            datasetURL: dataset,
            appContainerURL: container,
            startAccess: { starts += 1; return false },
            stopAccess: { stops += 1 }
        )
        lease.close()

        XCTAssertEqual(starts, 0)
        XCTAssertEqual(stops, 0)
    }

    func testExternalDatasetRetainsAndBalancesSecurityScope() throws {
        var starts = 0
        var stops = 0
        let lease = try DatasetAccessLease.acquire(
            datasetURL: URL(fileURLWithPath: "/private/var/mobile/Library/Mobile Documents/MH_01_easy"),
            appContainerURL: URL(fileURLWithPath: "/private/var/mobile/Containers/Data/Application/abc"),
            startAccess: { starts += 1; return true },
            stopAccess: { stops += 1 }
        )

        XCTAssertEqual(starts, 1)
        XCTAssertEqual(stops, 0)
        lease.close()
        lease.close()
        XCTAssertEqual(stops, 1)
    }

    func testExternalDatasetWithoutScopeIsRejected() {
        XCTAssertThrowsError(
            try DatasetAccessLease.acquire(
                datasetURL: URL(fileURLWithPath: "/external/MH_01_easy"),
                appContainerURL: URL(fileURLWithPath: "/container"),
                startAccess: { false },
                stopAccess: {}
            )
        ) { error in
            XCTAssertEqual(error as? DatasetAccessLease.AccessError, .securityScopeDenied)
        }
    }
}
