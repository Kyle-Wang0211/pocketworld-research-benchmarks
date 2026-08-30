import XCTest
@testable import VIOReplacementBench

final class SensorTransportLifecycleTests: XCTestCase {
    func testHappyPathAndInterruptionTransitions() throws {
        var lifecycle = SensorTransportLifecycle()

        try lifecycle.transition(to: .starting)
        try lifecycle.transition(to: .running)
        try lifecycle.transition(to: .interrupted)
        try lifecycle.transition(to: .running)
        try lifecycle.transition(to: .stopping)
        try lifecycle.transition(to: .sealed)
        try lifecycle.transition(to: .drained)

        XCTAssertEqual(lifecycle.state, .drained)
    }

    func testFailureCanStillSealAndDrain() throws {
        var lifecycle = SensorTransportLifecycle()
        try lifecycle.transition(to: .starting)
        try lifecycle.transition(to: .failed)
        try lifecycle.transition(to: .stopping)
        try lifecycle.transition(to: .sealed)
        try lifecycle.transition(to: .drained)
        XCTAssertEqual(lifecycle.state, .drained)
    }

    func testInvalidTransitionLeavesStateUnchanged() throws {
        var lifecycle = SensorTransportLifecycle()

        XCTAssertThrowsError(try lifecycle.transition(to: .running)) { error in
            XCTAssertEqual(
                error as? SensorTransportLifecycle.TransitionError,
                .invalid(from: .idle, to: .running)
            )
        }
        XCTAssertEqual(lifecycle.state, .idle)
    }
}
