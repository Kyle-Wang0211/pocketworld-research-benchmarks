import XCTest
@testable import VIOReplacementBench

final class VIOEngineSnapshotTests: XCTestCase {
    func testNeutralSnapshotPreservesBasaltQueueAndLossCounters() {
        var native = basalt_bench_snapshot_t()
        native.counters.camera_offered = 12
        native.counters.camera_accepted = 11
        native.counters.camera_dropped_queue_full = 1
        native.counters.imu_accepted = 30
        native.counters.poses_produced = 9
        native.optical_flow_input_queue_size = 2
        native.optical_flow_input_queue_capacity = 8
        native.vio_imu_queue_size = 3
        native.vio_imu_queue_capacity = 16

        let snapshot = VIOEngineSnapshot(basalt: native)
        XCTAssertEqual(snapshot.counters.cameraOffered, 12)
        XCTAssertEqual(snapshot.counters.cameraAccepted, 11)
        XCTAssertEqual(snapshot.counters.cameraDroppedQueueFull, 1)
        XCTAssertEqual(snapshot.counters.imuAccepted, 30)
        XCTAssertEqual(snapshot.counters.posesProduced, 9)
        XCTAssertEqual(snapshot.cameraInputQueue, .init(size: 2, capacity: 8, peak: 0))
        XCTAssertEqual(snapshot.imuInputQueue, .init(size: 3, capacity: 16, peak: 0))
    }
}
