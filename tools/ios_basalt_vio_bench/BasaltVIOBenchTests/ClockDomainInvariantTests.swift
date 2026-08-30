import XCTest
@testable import VIOReplacementBench

/// Regression tests for the cross-clock-domain defect found on device
/// 2026-08-29 and rooted out 2026-08-30.
///
/// `BasaltBench.mm` stamped publication times with `std::chrono::steady_clock`,
/// which Darwin maps to `mach_continuous_time` (includes sleep), while every
/// Swift-side timestamp came from `mach_absolute_time` (excludes sleep). The
/// difference is the device's accumulated sleep, and it was reported as latency.
final class ClockDomainInvariantTests: XCTestCase {

    /// The numbers actually observed on the phone. A 97 s run cannot contain a
    /// 81,219,463 ms latency; the run must be rejected, not scored.
    func testObservedDeviceFailureIsRejected() {
        let elapsed: UInt64 = 97_000_000_000
        let violation = ClockDomainInvariant.check(
            label: "pipeline_p95",
            latencyMilliseconds: 81_219_463.2,
            elapsedNanoseconds: elapsed
        )
        XCTAssertEqual(
            violation?.reason,
            "clock_domain_mismatch_pipeline_p95"
        )
    }

    /// The real first-pose latency was the difference between the two absurd
    /// numbers, and it must pass cleanly.
    func testRecoveredTrueLatencyIsAccepted() {
        let elapsed: UInt64 = 97_000_000_000
        XCTAssertNil(
            ClockDomainInvariant.check(
                label: "first_pose",
                latencyMilliseconds: 81_219_577.0 - 81_219_463.2,
                elapsedNanoseconds: elapsed
            )
        )
    }

    /// A violation short-circuits every other verdict: a run with mixed clocks
    /// has no meaningful loss accounting either.
    func testClockViolationOutranksCleanLossCounters() {
        let violation = ClockDomainInvariant.check(
            label: "first_pose",
            latencyNanoseconds: 81_219_577_000_000,
            elapsedNanoseconds: 97_000_000_000
        )
        XCTAssertNotNil(violation)
        XCTAssertEqual(
            LiveRunValidity.invalidReason(.zero, clockDomainViolation: violation),
            "clock_domain_mismatch_first_pose"
        )
        // Same counters, no violation: the run stays valid.
        XCTAssertNil(LiveRunValidity.invalidReason(.zero))
    }

    func testLatencyWithinSchedulingSlackIsAccepted() {
        let elapsed: UInt64 = 10_000_000_000
        XCTAssertNil(
            ClockDomainInvariant.check(
                label: "first_pose",
                latencyNanoseconds: elapsed + ClockDomainInvariant.schedulingSlackNanoseconds,
                elapsedNanoseconds: elapsed
            )
        )
    }

    func testLatencyOneNanosecondBeyondSlackIsRejected() {
        let elapsed: UInt64 = 10_000_000_000
        XCTAssertNotNil(
            ClockDomainInvariant.check(
                label: "first_pose",
                latencyNanoseconds: elapsed
                    + ClockDomainInvariant.schedulingSlackNanoseconds + 1,
                elapsedNanoseconds: elapsed
            )
        )
    }

    /// Non-finite and negative latencies are rejected, never clamped to zero.
    /// Clamping is what would have turned this defect into a plausible number.
    func testNonFiniteAndNegativeLatenciesAreRejected() {
        let elapsed: UInt64 = 10_000_000_000
        for value in [Double.nan, .infinity, -1.0, -0.0001] {
            XCTAssertNotNil(
                ClockDomainInvariant.check(
                    label: "first_pose",
                    latencyMilliseconds: value,
                    elapsedNanoseconds: elapsed
                ),
                "latency \(value) ms must invalidate the run"
            )
        }
    }

    /// A saturating ceiling keeps the check total instead of trapping.
    func testElapsedNearUInt64MaxDoesNotTrap() {
        XCTAssertNil(
            ClockDomainInvariant.check(
                label: "first_pose",
                latencyNanoseconds: UInt64.max,
                elapsedNanoseconds: UInt64.max - 1
            )
        )
    }

    // MARK: - The mapper itself must survive a large injected clock offset

    /// `MonotonicClockMapper` maps by delta from a per-source anchor, so an
    /// arbitrarily large offset between the raw source clock and the canonical
    /// domain cancels. This is the property that makes one domain achievable at
    /// all; without it the fix in `BasaltBench.mm` would not be sufficient.
    func testMapperCancelsLargeConstantSleepOffset() throws {
        // Anchor as if the device had been asleep 22.6 h: the raw source clock
        // reads far ahead of the canonical mach_absolute_time domain.
        let sleepOffsetSeconds = 81_219.577
        let canonicalAnchorNS: UInt64 = 42_087_301_077_208
        let mapper = MonotonicClockMapper(
            cameraHostTimeAnchorSeconds: sleepOffsetSeconds,
            coreMotionUptimeAnchorSeconds: sleepOffsetSeconds,
            monotonicAnchorNanoseconds: canonicalAnchorNS
        )

        // A frame captured 33.3 ms after the anchor must map to 33.3 ms after
        // the canonical anchor, not to the sleep offset.
        let mapped = try mapper.cameraNanoseconds(
            hostTimeSeconds: sleepOffsetSeconds + 0.0333
        )
        let delta = mapped - canonicalAnchorNS
        XCTAssertEqual(Double(delta), 33_300_000, accuracy: 1_000)

        let motion = try mapper.motionNanoseconds(
            uptimeSeconds: sleepOffsetSeconds + 0.005
        )
        XCTAssertEqual(Double(motion - canonicalAnchorNS), 5_000_000, accuracy: 1_000)
    }

    /// Mixing domains is exactly what the invariant exists to catch: a native
    /// publication stamped in continuous time against a capture stamped in
    /// absolute time yields the sleep accumulation, and that must invalidate.
    func testMixedDomainSubtractionIsCaughtNotScored() {
        let absoluteTimeCaptureNS: UInt64 = 42_087_301_077_208
        let continuousTimePublicationNS: UInt64 = 43_147_376_131_416
        let bogusLatency = continuousTimePublicationNS - absoluteTimeCaptureNS

        // 0.294 h of sleep, presented as a latency inside a 97 s run.
        XCTAssertGreaterThan(bogusLatency, 1_000_000_000_000)
        XCTAssertNotNil(
            ClockDomainInvariant.check(
                label: "pipeline",
                latencyNanoseconds: bogusLatency,
                elapsedNanoseconds: 97_000_000_000
            )
        )
    }
}
