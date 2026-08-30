import XCTest
@testable import VIOReplacementBench

final class ReplaySchedulerTests: XCTestCase {
    func testMaximumThroughputDoesNotConsultClockOrSleep() throws {
        let clock = FakeReplayClock(nowNanoseconds: 1_000)
        let events = makeEvents()
        var delivered: [Int64] = []

        try ReplayScheduler(mode: .maximumThroughput).run(events: events, clock: clock) {
            delivered.append($0.timestampNanoseconds)
        }

        XCTAssertEqual(delivered, [10, 110, 260])
        XCTAssertEqual(clock.nowCallCount, 0)
        XCTAssertEqual(clock.sleepDeadlines, [])
    }

    func testPacedUsesAbsoluteDatasetDeadlinesWithoutAccumulatingDrift() throws {
        let clock = FakeReplayClock(nowNanoseconds: 1_000)
        let events = makeEvents()
        var delivered: [Int64] = []

        try ReplayScheduler(mode: .paced).run(events: events, clock: clock) {
            delivered.append($0.timestampNanoseconds)
        }

        XCTAssertEqual(delivered, [10, 110, 260])
        XCTAssertEqual(clock.sleepDeadlines, [1_100, 1_250])
    }

    func testRejectsTimestampRegressionInPreloadedEvents() {
        let clock = FakeReplayClock(nowNanoseconds: 0)
        let events = [makeEvent(timestamp: 2), makeEvent(timestamp: 1)]

        XCTAssertThrowsError(
            try ReplayScheduler(mode: .paced).run(events: events, clock: clock) { _ in }
        ) { error in
            XCTAssertEqual(error as? ReplaySchedulerError, .timestampRegression(previous: 2, current: 1))
        }
    }

    private func makeEvents() -> [ReplayEvent] {
        [makeEvent(timestamp: 10), makeEvent(timestamp: 110), makeEvent(timestamp: 260)]
    }

    private func makeEvent(timestamp: Int64) -> ReplayEvent {
        .imu(
            EuRoCIMUSample(
                timestampNanoseconds: timestamp,
                gyroscopeRadiansPerSecond: Vector3(x: 0, y: 0, z: 0),
                accelerationMetersPerSecondSquared: Vector3(x: 0, y: 0, z: 9.81)
            )
        )
    }
}

private final class FakeReplayClock: ReplayClock {
    private(set) var now: UInt64
    private(set) var nowCallCount = 0
    private(set) var sleepDeadlines: [UInt64] = []

    init(nowNanoseconds: UInt64) {
        now = nowNanoseconds
    }

    func nowNanoseconds() -> UInt64 {
        nowCallCount += 1
        return now
    }

    func sleep(untilNanoseconds deadline: UInt64) throws {
        sleepDeadlines.append(deadline)
        now = deadline
    }
}
