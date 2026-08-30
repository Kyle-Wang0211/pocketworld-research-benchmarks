import XCTest
@testable import VIOReplacementBench

final class StatisticsTests: XCTestCase {
    func testCPUSecondsDeltaUsesExplicitEndpoints() {
        XCTAssertEqual(
            SystemMetricSampler.cpuSecondsDelta(start: 11.25, end: 14.75),
            3.5,
            accuracy: 0.000_001
        )
        XCTAssertEqual(SystemMetricSampler.cpuSecondsDelta(start: 14.75, end: 11.25), 0)
    }

    func testNearestRankPercentilesUseCompleteSample() {
        XCTAssertEqual(Statistics.nearestRankPercentile([5, 1, 4, 2, 3], percentile: 0.50), 3)
        XCTAssertEqual(Statistics.nearestRankPercentile([5, 1, 4, 2, 3], percentile: 0.95), 5)
    }

    func testEmptyPercentileIsNil() {
        XCTAssertNil(Statistics.nearestRankPercentile([], percentile: 0.95))
    }

    func testBatteryDeltaPreservesDischargeAndChargeSign() {
        XCTAssertEqual(
            Statistics.batteryLevelDelta(start: 0.90, end: 0.82),
            -0.08,
            accuracy: 1e-12
        )
        XCTAssertEqual(
            Statistics.batteryLevelDelta(start: 0.40, end: 0.47),
            0.07,
            accuracy: 1e-12
        )
    }

    func testPeakFootprintFailsClosedWhenAnyMeasurementIsUnavailable() {
        XCTAssertNil(Statistics.peakPhysicalFootprintMiB(samples: [
            metricSample(at: 0, thermal: "nominal", footprint: 1_048_576),
            metricSample(at: 1, thermal: "nominal", footprint: nil),
        ]))
        XCTAssertEqual(
            Statistics.peakPhysicalFootprintMiB(samples: [
                metricSample(at: 0, thermal: "nominal", footprint: 1_048_576),
                metricSample(at: 1, thermal: "nominal", footprint: 3_145_728),
            ]),
            3
        )
    }

    func testThermalDwellAccumulatesEachState() {
        var dwell = ThermalDwellAccumulator(initial: .nominal, at: 0)
        dwell.transition(to: .fair, at: 5)
        dwell.transition(to: .serious, at: 8)
        let result = dwell.finish(at: 10)
        XCTAssertEqual(result["nominal"], 5)
        XCTAssertEqual(result["fair"], 3)
        XCTAssertEqual(result["serious"], 2)
        XCTAssertEqual(dwell.firstSeriousSeconds, 8)
    }

    func testThermalDwellClosesMeasurementHeadAndTail() throws {
        let samples = [
            metricSample(at: 0, thermal: "nominal"),
            metricSample(at: 59, thermal: "fair"),
            metricSample(at: 61, thermal: "serious"),
            metricSample(at: 69, thermal: "critical"),
        ]

        let result = try XCTUnwrap(
            Statistics.thermalDwell(samples: samples, from: 60, to: 70)
        )

        XCTAssertEqual(result["fair"], 1)
        XCTAssertEqual(result["serious"], 8)
        XCTAssertEqual(result["critical"], 1)
    }

    func testThermalDwellRequiresSampleBracketingWindowStart() {
        XCTAssertNil(
            Statistics.thermalDwell(
                samples: [metricSample(at: 61, thermal: "serious")],
                from: 60,
                to: 70
            )
        )
    }

    private func metricSample(
        at seconds: Double,
        thermal: String,
        footprint: UInt64? = 1
    ) -> SystemMetricSample {
        SystemMetricSample(
            monotonicSeconds: seconds,
            processUserSeconds: 0,
            processSystemSeconds: 0,
            cpuCoreEquivalent: 0,
            physicalFootprintBytes: footprint,
            thermalState: thermal,
            batteryLevel: 1,
            batteryState: "full",
            lowPowerModeEnabled: false,
            appState: "active"
        )
    }
}
