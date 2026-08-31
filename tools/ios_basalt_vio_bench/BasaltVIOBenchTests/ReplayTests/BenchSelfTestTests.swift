import CryptoKit
import XCTest
@testable import VIOReplacementBench

/// This file was written but never added to the test target, so both purge
/// tests in it silently never ran -- while the purge they were meant to guard
/// destroyed an operator's capture.
final class BenchSelfTestTests: XCTestCase {}

extension BenchSelfTestTests {
    /// The purge destroyed an operator's hand-shot 30 s capture because it
    /// deleted every run directory. An unmarked directory must survive it.
    func testPurgeSpareseUnmarkedOperatorRuns() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("purge-\(UUID().uuidString)/VIOBenchRuns")
        let operatorRun = root.appendingPathComponent("run-operator")
        let selfTestRun = root.appendingPathComponent("run-selftest")
        try FileManager.default.createDirectory(at: operatorRun, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: selfTestRun, withIntermediateDirectories: true)
        try Data().write(
            to: selfTestRun.appendingPathComponent(BenchSelfTest.selfTestMarkerName)
        )

        let removed = BenchSelfTest.purgeRuns(rootURL: root)

        XCTAssertEqual(removed, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: operatorRun.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: selfTestRun.path))
    }
}

extension BenchSelfTestTests {
    /// Launch-time cleanup removes the harness's own runs and only those. An
    /// operator's capture has no marker and must survive every launch.
    func testLaunchPurgeRemovesOnlyMarkedRuns() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("launch-\(UUID().uuidString)/VIOBenchRuns")
        let mine = root.appendingPathComponent("run-selftest")
        let theirs = root.appendingPathComponent("run-operator")
        try FileManager.default.createDirectory(at: mine, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: theirs, withIntermediateDirectories: true)
        try Data().write(to: mine.appendingPathComponent(BenchSelfTest.selfTestMarkerName))

        XCTAssertEqual(BenchSelfTest.purgeRuns(rootURL: root), 1)
        XCTAssertFalse(FileManager.default.fileExists(atPath: mine.path))
        XCTAssertTrue(FileManager.default.fileExists(atPath: theirs.path))
    }
}

final class BenchmarkArtifactFinalizerMemoryTests: XCTestCase {
    /// Finalize read every artifact whole to hash it, so a 4.7 GB frame stream
    /// went into memory twice and the phone killed the app immediately after a
    /// clean capture -- the recording survived, its checksums did not. Hashing
    /// must not depend on an artifact's size.
    func testLargeArtifactIsHashedWithoutBeingReadWhole() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("finalize-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)

        // Bigger than one read chunk, so the streaming path is exercised.
        let bulk = Data(repeating: 0xAB, count: 10 * 1024 * 1024)
        try bulk.write(to: directory.appendingPathComponent("frames.bin"))
        for name in ["input_manifest.json", "receipt.json", "heartbeat.json",
                     "telemetry.jsonl", "diagnostics.json", "recording_manifest.json"] {
            try Data("{}".utf8).write(to: directory.appendingPathComponent(name))
        }

        try BenchmarkArtifactFinalizer.finalize(
            directoryURL: directory, runID: "mem", channel: .record
        )

        let sums = try String(
            contentsOf: directory.appendingPathComponent("SHA256SUMS"), encoding: .utf8
        )
        let expected = SHA256.hash(data: bulk).map { String(format: "%02x", $0) }.joined()
        XCTAssertTrue(sums.contains("\(expected)  frames.bin"),
                      "the streamed digest must equal the whole-file digest")

        let manifest = try JSONDecoder().decode(
            BenchmarkArtifactManifest.self,
            from: Data(contentsOf: directory.appendingPathComponent("artifact_manifest.json"))
        )
        let entry = try XCTUnwrap(manifest.artifacts.first { $0.path == "frames.bin" })
        XCTAssertEqual(entry.byteCount, bulk.count)
        XCTAssertEqual(entry.sha256, expected)
    }
}
