import Foundation
import XCTest
@testable import VIOReplacementBench

final class ArtifactFinalizerTests: XCTestCase {
    func testLiveFinalizerHashesRequiredArtifactsWithoutCircularManifestEntry() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        for (name, bytes) in [
            ("input_manifest.json", Data("input".utf8)),
            ("receipt.json", Data("receipt".utf8)),
            ("heartbeat.json", Data("heartbeat".utf8)),
            ("telemetry.jsonl", Data("telemetry".utf8)),
            ("diagnostics.json", Data("diagnostics".utf8)),
        ] {
            try bytes.write(to: directory.appendingPathComponent(name))
        }

        let runID = UUID().uuidString.lowercased()
        try BenchmarkArtifactFinalizer.finalize(
            directoryURL: directory,
            runID: runID,
            channel: .liveSoak
        )

        let manifestData = try Data(contentsOf: directory.appendingPathComponent("artifact_manifest.json"))
        let manifest = try JSONDecoder().decode(BenchmarkArtifactManifest.self, from: manifestData)
        XCTAssertEqual(manifest.runID, runID)
        XCTAssertEqual(Set(manifest.artifacts.map(\.path)), Set([
            "input_manifest.json", "receipt.json", "heartbeat.json",
            "telemetry.jsonl", "diagnostics.json", "SHA256SUMS",
        ]))
        XCTAssertFalse(manifest.artifacts.contains { $0.path == "artifact_manifest.json" })

        let sums = try String(
            contentsOf: directory.appendingPathComponent("SHA256SUMS"),
            encoding: .utf8
        )
        XCTAssertTrue(sums.contains("  input_manifest.json\n"))
        XCTAssertFalse(sums.contains("SHA256SUMS"))
        XCTAssertFalse(sums.contains("artifact_manifest.json"))
    }

    func testReplayFinalizerRejectsMissingPoses() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try Data("input".utf8).write(to: directory.appendingPathComponent("input_manifest.json"))
        try Data("receipt".utf8).write(to: directory.appendingPathComponent("receipt.json"))

        XCTAssertThrowsError(
            try BenchmarkArtifactFinalizer.finalize(
                directoryURL: directory,
                runID: UUID().uuidString.lowercased(),
                channel: .replayPaced
            )
        )
    }
}
