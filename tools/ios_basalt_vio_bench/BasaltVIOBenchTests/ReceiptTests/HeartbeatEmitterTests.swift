import XCTest
@testable import VIOReplacementBench

final class HeartbeatEmitterTests: XCTestCase {
    func testSequenceAdvancesOnlyWhenDue() {
        var schedule = HeartbeatSchedule(intervalNanoseconds: 5_000_000_000)
        XCTAssertEqual(schedule.consumeSequenceIfDue(nowNanoseconds: 100), 0)
        XCTAssertNil(schedule.consumeSequenceIfDue(nowNanoseconds: 4_999_999_999))
        XCTAssertEqual(schedule.consumeSequenceIfDue(nowNanoseconds: 5_000_000_100), 1)
        XCTAssertNil(schedule.consumeSequenceIfDue(nowNanoseconds: 9_000_000_000))
        XCTAssertEqual(schedule.consumeSequenceIfDue(nowNanoseconds: 10_000_000_100), 2)
    }

    func testCanContinueAfterStartedReceiptHeartbeat() {
        var schedule = HeartbeatSchedule(
            intervalNanoseconds: 5_000_000_000,
            startingSequence: 1,
            firstDeadlineNanoseconds: 6_000_000_000
        )
        XCTAssertNil(schedule.consumeSequenceIfDue(nowNanoseconds: 5_999_999_999))
        XCTAssertEqual(schedule.consumeSequenceIfDue(nowNanoseconds: 6_000_000_000), 1)
    }
}
