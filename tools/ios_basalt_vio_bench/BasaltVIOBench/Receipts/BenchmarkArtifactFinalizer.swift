import Foundation

struct BenchmarkArtifactEntry: Codable, Equatable {
    let path: String
    let role: String
    let byteCount: Int
    let sha256: String

    private enum CodingKeys: String, CodingKey {
        case path, role, sha256
        case byteCount = "byte_count"
    }
}

struct BenchmarkArtifactManifest: Codable, Equatable {
    let schemaVersion: Int
    let runID: String
    let generatedAtUTC: String
    let artifacts: [BenchmarkArtifactEntry]

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case runID = "run_id"
        case generatedAtUTC = "generated_at_utc"
        case artifacts
    }
}

enum BenchmarkArtifactFinalizerError: LocalizedError {
    case missingRequiredArtifact(String)
    case unsafeArtifactPath(String)

    var errorDescription: String? {
        switch self {
        case .missingRequiredArtifact(let path): return "缺少实验产物：\(path)"
        case .unsafeArtifactPath(let path): return "实验产物路径不安全：\(path)"
        }
    }
}

enum BenchmarkArtifactFinalizer {
    private static let manifestName = "artifact_manifest.json"
    private static let checksumsName = "SHA256SUMS"

    static func finalize(
        directoryURL: URL,
        runID: String,
        channel: RunReceiptChannel,
        fileManager: FileManager = .default
    ) throws {
        for required in requiredArtifacts(for: channel) where
            !fileManager.fileExists(atPath: directoryURL.appendingPathComponent(required).path) {
            throw BenchmarkArtifactFinalizerError.missingRequiredArtifact(required)
        }

        let excluded = Set([manifestName, checksumsName])
        let contentNames = try fileManager.contentsOfDirectory(
            at: directoryURL,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        )
        .filter { url in
            !excluded.contains(url.lastPathComponent)
                && (try? url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true
        }
        .map(\.lastPathComponent)
        .sorted()

        var checksumRows: [String] = []
        for name in contentNames {
            try validateSafeFilename(name)
            let data = try Data(contentsOf: directoryURL.appendingPathComponent(name))
            checksumRows.append("\(RunReceiptHash.sha256Hex(data))  \(name)")
        }
        let checksums = Data((checksumRows.joined(separator: "\n") + "\n").utf8)
        try checksums.write(
            to: directoryURL.appendingPathComponent(checksumsName),
            options: .atomic
        )

        let artifactNames = (contentNames + [checksumsName]).sorted()
        let artifacts = try artifactNames.map { name -> BenchmarkArtifactEntry in
            try validateSafeFilename(name)
            let data = try Data(contentsOf: directoryURL.appendingPathComponent(name))
            return BenchmarkArtifactEntry(
                path: name,
                role: role(for: name),
                byteCount: data.count,
                sha256: RunReceiptHash.sha256Hex(data)
            )
        }
        let manifest = BenchmarkArtifactManifest(
            schemaVersion: 1,
            runID: runID,
            generatedAtUTC: BenchmarkRunPreparation.utcTimestamp(),
            artifacts: artifacts
        )
        try RunReceiptJSON.encoder.encode(manifest).write(
            to: directoryURL.appendingPathComponent(manifestName),
            options: .atomic
        )
    }

    private static func requiredArtifacts(for channel: RunReceiptChannel) -> [String] {
        switch channel {
        case .record:
            return ["input_manifest.json", "receipt.json", "heartbeat.json", "telemetry.jsonl", "diagnostics.json", "recording_manifest.json", "SHA256SUMS"]
        case .liveSoak:
            return ["input_manifest.json", "receipt.json", "heartbeat.json", "telemetry.jsonl", "diagnostics.json"]
        case .replayDeviceRecording:
            return ["input_manifest.json", "poses.tum", "receipt.json", "heartbeat.json", "diagnostics.json"]
        case .replayPaced, .replayMax:
            return ["input_manifest.json", "poses.tum", "receipt.json", "heartbeat.json", "diagnostics.json"]
        }
    }

    private static func role(for name: String) -> String {
        switch name {
        case "input_manifest.json": return "input_manifest"
        case "poses.tum": return "poses"
        case "receipt.json": return "receipt"
        case "heartbeat.json": return "heartbeat"
        case "telemetry.jsonl": return "telemetry"
        case "diagnostics.json": return "diagnostics"
        case checksumsName: return "checksums"
        default: return "other"
        }
    }

    private static func validateSafeFilename(_ name: String) throws {
        guard !name.isEmpty,
              name != ".", name != "..",
              !name.contains("/"), !name.contains("\\") else {
            throw BenchmarkArtifactFinalizerError.unsafeArtifactPath(name)
        }
    }
}
