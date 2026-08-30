import Foundation

struct GateVerdict: Equatable {
    let passed: Bool
    let failedReasons: [String]
}

enum BenchGateEvaluator {
    static func live(
        firstUsablePoseLatencyMilliseconds: Double,
        processedFPS: Double,
        p95LatencyMilliseconds: Double,
        appDropRate: Double,
        thermalCriticalSeconds: Double,
        thermalSeriousSeconds: Double,
        peakFootprintMB: Double,
        finitePoseRatio: Double,
        processedFPSMinimum: Double = 27
    ) -> GateVerdict {
        var failures: [String] = []
        if firstUsablePoseLatencyMilliseconds > 1_800 {
            failures.append("first_usable_pose_latency_ms>1800.0")
        }
        if processedFPS < processedFPSMinimum {
            failures.append("processed_fps<\(processedFPSMinimum)")
        }
        if p95LatencyMilliseconds > 66.7 { failures.append("p95_pipeline_latency_ms>66.7") }
        if appDropRate > 0 { failures.append("app_drop_rate>0") }
        if thermalCriticalSeconds > 0 { failures.append("thermal_critical_seconds>0") }
        if thermalSeriousSeconds > 0 { failures.append("thermal_serious_seconds>0") }
        if peakFootprintMB > 750 { failures.append("peak_phys_footprint_mb>750") }
        if finitePoseRatio < 0.995 { failures.append("finite_pose_ratio<0.995") }
        return GateVerdict(passed: failures.isEmpty, failedReasons: failures)
    }

    static func replay(_ metrics: TrajectoryMetrics) -> GateVerdict {
        var failures: [String] = []
        if metrics.ateRMSEMeters > 0.10 { failures.append("ate_rmse_m>0.10") }
        if metrics.rpeTranslationRMSEMeters > 0.05 {
            failures.append("rpe_translation_rmse_m>0.05")
        }
        if metrics.rpeRotationRMSEDegrees > 5 {
            failures.append("rpe_rotation_rmse_deg>5")
        }
        if metrics.groundTruthCoverage < 0.99 {
            failures.append("ground_truth_coverage<0.99")
        }
        return GateVerdict(passed: failures.isEmpty, failedReasons: failures)
    }
}
