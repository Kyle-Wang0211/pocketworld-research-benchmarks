import Foundation
import XCTest
@testable import VIOReplacementBench

final class ApplicationActivityLatchTests: XCTestCase {
    func testLatchesEveryForegroundViolationBetweenTelemetrySamples() {
        let center = NotificationCenter()
        let resign = Notification.Name("bench.test.will-resign")
        let background = Notification.Name("bench.test.did-enter-background")
        let latch = ApplicationActivityLatch(
            center: center,
            willResignActiveName: resign,
            didEnterBackgroundName: background
        )

        latch.start(initiallyActive: true)
        center.post(name: resign, object: nil)
        center.post(name: background, object: nil)

        XCTAssertEqual(latch.snapshot().violationCount, 2)
    }

    func testInactiveStartAndPostStopNotificationsAreFailClosed() {
        let center = NotificationCenter()
        let resign = Notification.Name("bench.test.will-resign")
        let background = Notification.Name("bench.test.did-enter-background")
        let latch = ApplicationActivityLatch(
            center: center,
            willResignActiveName: resign,
            didEnterBackgroundName: background
        )

        latch.start(initiallyActive: false)
        latch.stop()
        center.post(name: resign, object: nil)

        XCTAssertEqual(latch.snapshot().violationCount, 1)
    }
}
