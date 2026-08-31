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

final class CalibrationMaterializerYAMLTests: XCTestCase {
    /// xrslam's calibration is YAML. Running it through the JSON substitution
    /// threw before the started receipt existed, so a replay produced a run
    /// directory with nothing in it and no stated reason -- for twenty minutes
    /// that looked like the engine hanging.
    func testYAMLCalibrationTakesTheRecordingsIntrinsicsAndResolution() throws {
        let frozen = """
        cam0:
          T_BS:
            data: [1.0, 0.0]
          resolution: [640, 480]
          camera_model: pinhole
          intrinsics: [448.96781816245402, 449.14399528627763, 321.34605334072404, 240.71641804985396]
          extrinsic:
            q_bc: [-0.7071068, 0.7071068, 0, 0]
        """
        let out = try CalibrationMaterializer.deviceRecordingYAML(
            from: Data(frozen.utf8),
            intrinsics: DeviceRecordingIntrinsics(
                fx: 1341.84, fy: 1341.84, cx: 957.50, cy: 718.91,
                source: "ARFrame.camera.intrinsics", crossCheckPassed: true
            ),
            width: 1920,
            height: 1440
        )
        let text = try XCTUnwrap(String(data: out, encoding: .utf8))

        XCTAssertTrue(text.contains("resolution: [1920, 1440]"))
        XCTAssertTrue(text.contains("intrinsics: [1341.84, 1341.84, 957.5, 718.91]"))
        // The mount transform is a rigid property and must survive untouched.
        XCTAssertTrue(text.contains("q_bc: [-0.7071068, 0.7071068, 0, 0]"))
        XCTAssertTrue(text.contains("camera_model: pinhole"))
        XCTAssertFalse(text.contains("640, 480"))
    }

    func testYAMLWithoutTheExpectedKeysIsRefused() {
        XCTAssertThrowsError(
            try CalibrationMaterializer.deviceRecordingYAML(
                from: Data("cam0:\n  camera_model: pinhole\n".utf8),
                intrinsics: DeviceRecordingIntrinsics(
                    fx: 1, fy: 1, cx: 1, cy: 1,
                    source: "ARFrame.camera.intrinsics", crossCheckPassed: true
                ),
                width: 1920, height: 1440
            )
        )
    }
}

final class CRLFParsingTests: XCTestCase {
    /// EuRoC ships CRLF. Swift iterates strings by grapheme cluster and CRLF is
    /// one cluster, so splitting on the character "\n" finds no separator at all
    /// and returns the file as a single line -- which, for a CSV whose first line
    /// is a comment, parses as zero rows. The EuRoC camera index was refused as
    /// empty for exactly this reason while the file on disk was intact.
    func testCRLFAndLFSplitTheSame() {
        let lf = "#header\n1,a\n2,b\n"
        let crlf = "#header\r\n1,a\r\n2,b\r\n"

        func rows(_ text: String) -> [[String]] {
            text.split(omittingEmptySubsequences: false, whereSeparator: \.isNewline)
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty && !$0.hasPrefix("#") }
                .map { $0.split(separator: ",").map(String.init) }
        }
        XCTAssertEqual(rows(lf), [["1", "a"], ["2", "b"]])
        XCTAssertEqual(rows(crlf), rows(lf), "CRLF must parse identically to LF")

        // The old predicate, kept to show what it did rather than described.
        let oldCRLF = crlf.split(separator: "\n", omittingEmptySubsequences: false)
        XCTAssertEqual(oldCRLF.count, 1, "splitting CRLF on \"\\n\" yields one line")
    }
}
