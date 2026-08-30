import XCTest
@testable import VIOReplacementBench

final class BoundedSensorHandoffTests: XCTestCase {
    func testFullQueueDropsNewestAndAccountsForEveryOffer() {
        let handoff = BoundedSensorHandoff<Int>(capacity: 2)

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
        let handoff = BoundedSensorHandoff<Int>(capacity: 3)
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
        let handoff = BoundedSensorHandoff<Int>(capacity: 1)

        XCTAssertEqual(handoff.seal(), .sealed)
        XCTAssertEqual(handoff.state, .sealed)

        let batch = handoff.drain(maxCount: 1)
        XCTAssertTrue(batch.items.isEmpty)
        XCTAssertTrue(batch.isSealedAndDrained)
        XCTAssertEqual(handoff.state, .drained)
    }

    func testDrainLimitMustBePositive() {
        let handoff = BoundedSensorHandoff<Int>(capacity: 1)
        XCTAssertEqual(handoff.offer(7), .accepted)

        let batch = handoff.drain(maxCount: 0)
        XCTAssertTrue(batch.items.isEmpty)
        XCTAssertFalse(batch.isSealedAndDrained)
        XCTAssertEqual(handoff.snapshot().depth, 1)
    }
}

/// Regression tests for the contention loss found on device 2026-08-30.
///
/// A 300 s Basalt run accepted 8,984 of 8,985 frames with the queue peaking at 1
/// against capacity 10. The single lost frame was not backpressure: `offer` used
/// `lock.try()` and abandoned the sample on any collision, while the queue was
/// 90 percent empty. Under the zero-loss gate that frame invalidated the run,
/// and at ~0.011 percent the same outcome is near-certain in any five-minute
/// capture. Dropping on contention and requiring zero loss cannot both hold.
final class BoundedSensorHandoffContentionTests: XCTestCase {

    /// The consumer spins on `drain` to maximise contention while the producer
    /// stays slower than it, so a full queue is impossible and contention is the
    /// only way a sample could be lost.
    func testNoSampleIsLostToContention() {
        let capacity = 10
        let total = 20_000
        let handoff = BoundedSensorHandoff<Int>(capacity: capacity)
        let guardLock = NSLock()
        var consumed: [Int] = []
        consumed.reserveCapacity(total)
        let finished = expectation(description: "consumer drained every sample")

        DispatchQueue.global(qos: .userInitiated).async {
            var count = 0
            while count < total {
                let batch = handoff.drain(maxCount: capacity)
                if !batch.items.isEmpty {
                    guardLock.lock()
                    consumed.append(contentsOf: batch.items)
                    guardLock.unlock()
                    count += batch.items.count
                }
            }
            finished.fulfill()
        }

        var accepted = 0
        for value in 0..<total {
            if case .accepted = handoff.offer(value) { accepted += 1 }
            usleep(20)
        }
        wait(for: [finished], timeout: 60)

        let snapshot = handoff.snapshot()
        XCTAssertEqual(snapshot.droppedContended, 0, "contention must never lose a sample")
        XCTAssertEqual(snapshot.droppedFull, 0, "producer stayed behind the consumer")
        XCTAssertEqual(accepted, total)
        guardLock.lock()
        let received = consumed
        guardLock.unlock()
        XCTAssertEqual(received.count, total)
        XCTAssertEqual(received, Array(0..<total), "order must be intact with no gaps")
        // Mirrors the device run, where the queue peaked at 1 of 10.
        XCTAssertLessThanOrEqual(snapshot.highWatermark, capacity)
    }

    /// Backpressure is still a drop. Taking the lock instead of abandoning the
    /// sample must not quietly turn a bounded queue into an unbounded one.
    func testGenuinelyFullQueueStillDrops() {
        let handoff = BoundedSensorHandoff<Int>(capacity: 3)
        for value in 0..<3 { _ = handoff.offer(value) }
        XCTAssertEqual(handoff.offer(99), .droppedFull)
        XCTAssertEqual(
            handoff.snapshot().droppedContended, 0,
            "a full queue must not be miscounted as contention"
        )
    }
}
