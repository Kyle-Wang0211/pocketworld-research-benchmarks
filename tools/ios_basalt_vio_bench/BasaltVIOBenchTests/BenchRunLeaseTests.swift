import XCTest
@testable import VIOReplacementBench

final class BenchRunLeaseTests: XCTestCase {
    override func tearDown() {
        BenchRunLease.forceResetForTesting()
        super.tearDown()
    }

    func testOnlyOneBackendCanOwnTheProcessAtATime() throws {
        let basalt = try XCTUnwrap(BenchRunLease.acquire(backend: .basalt))
        XCTAssertNil(BenchRunLease.acquire(backend: .xrslam))
        XCTAssertNil(BenchRunLease.acquire(backend: .arkit))

        let released = basalt.release()
        XCTAssertEqual(released.selectedArm, BenchBackend.basalt.id)
        XCTAssertEqual(released.maxSimultaneousActiveArms, 1)
        XCTAssertEqual(released.overlapDurationNanoseconds, 0)
        XCTAssertFalse(released.engineSessionActive)
        XCTAssertFalse(released.arSessionActive)
        XCTAssertFalse(released.avFoundationTransportActive)
        XCTAssertNotNil(released.releasedNanoseconds)

        let arkit = try XCTUnwrap(BenchRunLease.acquire(backend: .arkit))
        XCTAssertEqual(arkit.snapshot().selectedArm, BenchBackend.arkit.id)
        _ = arkit.release()
    }

    func testReleaseIsIdempotentAndCarriesActuallyObservedActivity() throws {
        let token = try XCTUnwrap(BenchRunLease.acquire(backend: .xrslam))
        try token.recordEngineSessionStarted()
        try token.recordAVFoundationTransportStarted()
        let first = token.release()
        let second = token.release()
        XCTAssertEqual(first, second)
        XCTAssertFalse(first.arSessionActive)
        XCTAssertTrue(first.avFoundationTransportActive)
        XCTAssertTrue(first.engineSessionActive)
    }

    func testARKitArmRejectsNativeEngineAndTransportActivity() throws {
        let token = try XCTUnwrap(BenchRunLease.acquire(backend: .arkit))
        XCTAssertThrowsError(try token.recordEngineSessionStarted())
        XCTAssertThrowsError(try token.recordAVFoundationTransportStarted())
        try token.recordARSessionStarted()
        XCTAssertThrowsError(try token.recordARSessionStarted())

        let receipt = token.release()
        XCTAssertTrue(receipt.arSessionActive)
        XCTAssertFalse(receipt.engineSessionActive)
        XCTAssertFalse(receipt.avFoundationTransportActive)
    }

    func testReplayEngineDoesNotClaimLiveCameraTransport() throws {
        let token = try XCTUnwrap(BenchRunLease.acquire(backend: .basalt))
        try token.recordEngineSessionStarted()
        let receipt = token.release()
        XCTAssertTrue(receipt.engineSessionActive)
        XCTAssertFalse(receipt.arSessionActive)
        XCTAssertFalse(receipt.avFoundationTransportActive)
    }

    func testEveryOrderedArmPairRequiresHandoffBeforeTheSecondCanStart() throws {
        for firstBackend in BenchBackend.allCases {
            for secondBackend in BenchBackend.allCases {
                BenchRunLease.forceResetForTesting()
                let first = try XCTUnwrap(BenchRunLease.acquire(backend: firstBackend))
                XCTAssertNil(
                    BenchRunLease.acquire(backend: secondBackend),
                    "\(secondBackend.id) overlapped \(firstBackend.id)"
                )
                _ = first.release()
                let second = try XCTUnwrap(BenchRunLease.acquire(backend: secondBackend))
                XCTAssertEqual(second.snapshot().selectedArm, secondBackend.id)
                _ = second.release()
            }
        }
    }
}
