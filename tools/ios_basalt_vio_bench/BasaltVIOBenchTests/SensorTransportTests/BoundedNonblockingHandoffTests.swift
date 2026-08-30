import XCTest
@testable import VIOReplacementBench

final class BoundedNonblockingHandoffTests: XCTestCase {
    func testFullQueueDropsNewestAndAccountsForEveryOffer() {
        let handoff = BoundedNonblockingHandoff<Int>(capacity: 2)

        XCTAssertEqual(handoff.offer(10), .accepted)
        XCTAssertEqual(handoff.offer(20), .accepted)
        XCTAssertEqual(handoff.offer(30), .droppedFull)

        let snapshot = handoff.snapshot()
        XCTAssertEqual(snapshot.accepted, 2)
        XCTAssertEqual(snapshot.droppedFull, 1)
        XCTAssertEqual(snapshot.rejectedSealed, 0)
        XCTAssertEqual(snapshot.depth, 2)
        XCTAssertEqual(snapshot.highWatermark, 2)
    }

    func testSealRejectsNewInputButAllowsExistingItemsToDrain() {
        let handoff = BoundedNonblockingHandoff<Int>(capacity: 3)
        XCTAssertEqual(handoff.offer(1), .accepted)
        XCTAssertEqual(handoff.offer(2), .accepted)

        XCTAssertEqual(handoff.seal(), .sealed)
        XCTAssertEqual(handoff.offer(3), .rejectedSealed)

        let first = handoff.drain(maxCount: 1)
        XCTAssertEqual(first.items, [1])
        XCTAssertFalse(first.isSealedAndDrained)
        XCTAssertEqual(handoff.state, .sealed)

        let second = handoff.drain(maxCount: 8)
        XCTAssertEqual(second.items, [2])
        XCTAssertTrue(second.isSealedAndDrained)
        XCTAssertEqual(handoff.state, .drained)
        XCTAssertEqual(handoff.offer(4), .rejectedSealed)
    }

    func testEmptySealedQueueBecomesDrainedOnlyWhenConsumerObservesDrain() {
        let handoff = BoundedNonblockingHandoff<Int>(capacity: 1)

        XCTAssertEqual(handoff.seal(), .sealed)
        XCTAssertEqual(handoff.state, .sealed)

        let batch = handoff.drain(maxCount: 1)
        XCTAssertTrue(batch.items.isEmpty)
        XCTAssertTrue(batch.isSealedAndDrained)
        XCTAssertEqual(handoff.state, .drained)
    }

    func testDrainLimitMustBePositive() {
        let handoff = BoundedNonblockingHandoff<Int>(capacity: 1)
        XCTAssertEqual(handoff.offer(7), .accepted)

        let batch = handoff.drain(maxCount: 0)
        XCTAssertTrue(batch.items.isEmpty)
        XCTAssertFalse(batch.isSealedAndDrained)
        XCTAssertEqual(handoff.snapshot().depth, 1)
    }
}
