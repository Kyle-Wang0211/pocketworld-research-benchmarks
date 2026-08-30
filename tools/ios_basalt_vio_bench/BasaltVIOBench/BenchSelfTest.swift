import Foundation
import UIKit

/// Lets the bench be exercised and inspected without anyone touching the screen.
///
/// Every defect in the record path so far -- the resolution/calibration mismatch,
/// the unstartable mode pairing, the ARKit-replay guard, the four `liveSoak`
/// proxies, the disk-space refusal -- was found by asking the operator to run it
/// and report back. That is the wrong test harness: each round cost a person
/// several minutes and produced one bit of information.
///
/// Two capabilities replace that:
///
/// * a preflight file written on every launch, so device state that no host tool
///   reports (free space in particular) can be read straight out of the app
///   container;
/// * a launch-argument auto-run, so a short recording can be driven end to end
///   from the command line and its artifacts checked before anyone is asked for
///   a five-minute capture.
enum BenchSelfTest {

    // MARK: - Preflight

    /// Written at launch. `devicectl` reports total capacity but never free
    /// space, and free space is exactly what refused the last recording.
    static func writePreflight() {
        let documents = URL.documentsDirectory
        let values = try? documents.resourceValues(
            forKeys: [.volumeAvailableCapacityForImportantUsageKey]
        )
        let available = Int64(values?.volumeAvailableCapacityForImportantUsage ?? 0)
        let projected300 = DeviceRecordingWriter.projectedByteCount(seconds: 300)
        let headroom = DeviceRecordingWriter.freeSpaceHeadroomBytes

        var payload: [String: Any] = [
            "written_at_utc": ISO8601DateFormatter().string(from: Date()),
            "available_bytes_for_important_usage": available,
            "available_gib": Double(available) / 1_073_741_824,
            "recording_headroom_bytes": headroom,
            "projected_300s_bytes": projected300,
            "projected_300s_gib": Double(projected300) / 1_073_741_824,
            "can_record_300s": available >= projected300 + headroom,
            "scoring_resolution": [
                BenchResolution.scoring.width, BenchResolution.scoring.height,
            ],
            "experiment_id": BenchExperimentIdentity.experimentID,
            "thermal_state": ProcessInfo.processInfo.thermalState.rawValue,
        ]
        // The longest recording this device could take right now, so a refusal
        // comes with an actionable number instead of only a complaint.
        let usable = max(0, available - headroom)
        let bytesPerSecond = Int64(
            DeviceRecordingCameraFormat.scoring.bytesPerFrame
        ) * 30
        payload["max_recordable_seconds"] = bytesPerSecond > 0
            ? Int(usable / bytesPerSecond)
            : 0

        guard let data = try? JSONSerialization.data(
            withJSONObject: payload,
            options: [.prettyPrinted, .sortedKeys]
        ) else { return }
        try? data.write(
            to: documents.appendingPathComponent("preflight.json"),
            options: .atomic
        )
    }

    /// `-PWPurgeRuns` — deletes every run directory.
    ///
    /// A 10 s recording at 1920x1440 is 1.5 GB, so a handful of self-test runs
    /// can consume the headroom the real capture needs. Without this the only way
    /// to reclaim it is deleting the app, which would take the diagnostic runs
    /// with it.
    @discardableResult
    static func purgeRunsIfRequested(
        arguments: [String] = ProcessInfo.processInfo.arguments
    ) -> Int {
        guard arguments.contains("-PWPurgeRuns") else { return 0 }
        let root = URL.documentsDirectory.appendingPathComponent("VIOBenchRuns")
        let entries = (try? FileManager.default.contentsOfDirectory(
            at: root, includingPropertiesForKeys: nil
        )) ?? []
        var removed = 0
        for entry in entries where entry.lastPathComponent.hasPrefix("run-") {
            if (try? FileManager.default.removeItem(at: entry)) != nil { removed += 1 }
        }
        return removed
    }

    // MARK: - Auto-run

    struct AutoRun: Equatable {
        let backend: BenchBackend
        let mode: BenchMode
        let seconds: Double
    }

    /// `-PWAutoRun record -PWAutoRunSeconds 20`
    ///
    /// Absent the argument this returns nil and the app behaves normally, so the
    /// hook cannot affect an operator-driven run.
    static func parse(arguments: [String] = ProcessInfo.processInfo.arguments) -> AutoRun? {
        guard let index = arguments.firstIndex(of: "-PWAutoRun"),
              index + 1 < arguments.count,
              let mode = BenchMode(rawValue: arguments[index + 1]) else {
            return nil
        }
        var seconds = 20.0
        if let secondsIndex = arguments.firstIndex(of: "-PWAutoRunSeconds"),
           secondsIndex + 1 < arguments.count,
           let parsed = Double(arguments[secondsIndex + 1]),
           parsed > 0 {
            seconds = parsed
        }
        // `record` is ARKit-only by construction; anything else runs on Basalt
        // unless a backend is named.
        var backend: BenchBackend = mode == .record ? .arkit : .basalt
        if let backendIndex = arguments.firstIndex(of: "-PWAutoRunBackend"),
           backendIndex + 1 < arguments.count,
           let parsed = BenchBackend.allCases.first(
               where: { $0.id == arguments[backendIndex + 1] }
           ) {
            backend = parsed
        }
        return AutoRun(backend: backend, mode: mode, seconds: seconds)
    }
}
