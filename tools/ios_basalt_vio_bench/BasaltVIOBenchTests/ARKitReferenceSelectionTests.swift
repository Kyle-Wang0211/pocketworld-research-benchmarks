import XCTest
@testable import VIOReplacementBench

/// The live gates judge a candidate against an ARKit reference receipt found on
/// the device. Until 2026-09-16 that receipt was chosen by directory
/// modification time, which is not the run's own clock -- a directory re-copied
/// off the device outranks a later run. On the bench phone it selected a 30 s
/// run from 08-31 (first pose 2874.9 ms) over the 300 s baseline from 09-15
/// (1762.1 ms), so a candidate was measured against the worst and shortest
/// ARKit run present, and the receipt recorded only the number.
final class ARKitReferenceSelectionTests: XCTestCase {
    private func writeRun(
        in root: URL,
        directory: String,
        runID: String,
        engineID: String,
        startedAtUTC: String,
        firstPoseMS: Double,
        durationSeconds: Double,
        modified: Date
    ) throws {
        let dir = root.appendingPathComponent(directory)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let receipt: [String: Any] = [
            "run_id": runID,
            "started_at_utc": startedAtUTC,
            "app": ["engine_id": engineID],
            "metrics": [
                "first_usable_pose_latency_ms": firstPoseMS,
                "measurement_duration_seconds": durationSeconds,
            ],
        ]
        let url = dir.appendingPathComponent("receipt.json")
        try JSONSerialization.data(withJSONObject: receipt).write(to: url)
        try FileManager.default.setAttributes([.modificationDate: modified], ofItemAtPath: dir.path)
    }

    /// The oldest run is given the newest modification date, which is exactly the
    /// shape that misled the old picker.
    func testPicksLatestByStartedAtNotByDirectoryModificationDate() throws {
        let root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("arkitref-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        try writeRun(in: root, directory: "run-old", runID: "old",
                     engineID: "arkit_reference", startedAtUTC: "2026-08-31T04:07:47.000Z",
                     firstPoseMS: 2874.9, durationSeconds: 30,
                     modified: Date(timeIntervalSince1970: 9_000_000_000))
        try writeRun(in: root, directory: "run-new", runID: "new",
                     engineID: "arkit_reference", startedAtUTC: "2026-09-15T01:34:46.000Z",
                     firstPoseMS: 1762.1, durationSeconds: 300,
                     modified: Date(timeIntervalSince1970: 1_000_000_000))

        let reference = try XCTUnwrap(BenchmarkCoordinator.arkitReference(runsRoot: root))
        XCTAssertEqual(reference.runID, "new")
        XCTAssertEqual(reference.firstUsablePoseLatencyMS, 1762.1, accuracy: 1e-9)
        XCTAssertEqual(reference.measurementDurationSeconds, 300, accuracy: 1e-9)
    }

    /// Negative control: a non-ARKit receipt must never become the reference,
    /// however new it is.
    func testIgnoresNonARKitRuns() throws {
        let root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("arkitref-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        try writeRun(in: root, directory: "run-arkit", runID: "arkit",
                     engineID: "arkit_reference", startedAtUTC: "2026-09-01T00:00:00.000Z",
                     firstPoseMS: 1500, durationSeconds: 300,
                     modified: Date(timeIntervalSince1970: 1_000_000_000))
        try writeRun(in: root, directory: "run-xrslam", runID: "xrslam",
                     engineID: "xrslam", startedAtUTC: "2026-09-16T00:00:00.000Z",
                     firstPoseMS: 1, durationSeconds: 300,
                     modified: Date(timeIntervalSince1970: 9_000_000_000))

        let reference = try XCTUnwrap(BenchmarkCoordinator.arkitReference(runsRoot: root))
        XCTAssertEqual(reference.runID, "arkit")
    }

    func testReturnsNilWhenNoReferenceExists() throws {
        let root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("arkitref-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        XCTAssertNil(BenchmarkCoordinator.arkitReference(runsRoot: root))
    }
}
