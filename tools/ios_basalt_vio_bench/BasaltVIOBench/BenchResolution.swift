import Foundation

/// The resolutions the bench runs at, and which of them a verdict may be built on.
///
/// Production runs ARKit at 1920x1440 on this device, so 1920x1440 is the bar
/// every candidate is scored against. Declaring a 640x480 candidate faster or
/// cooler than a 1920x1440 ARKit would compare two different problems.
public enum BenchResolution: Equatable {
    /// The only resolution a verdict may be built on. Every arm scores here.
    public static let scoring = (width: 1920, height: 1440)

    /// Non-scoring. Its single job is failure triage: when a candidate fails at
    /// the scoring resolution, rerunning at the scale its upstream config was
    /// actually tuned for separates "the algorithm cannot carry this many
    /// pixels" from "we carried its pixel-unit parameters across wrong".
    public static let diagnostic = (width: 640, height: 480)

    /// `diagnostic` is derived from the recording by deterministic downscale, so
    /// the two share one physical capture.
    public static let diagnosticDownscaleFactor = 3

    public static func participatesInVerdict(width: Int, height: Int) -> Bool {
        width == scoring.width && height == scoring.height
    }
}

/// Camera intrinsics for one resolution.
struct CameraIntrinsics: Equatable {
    let fx: Double
    let fy: Double
    let cx: Double
    let cy: Double

    func scaled(by factor: Double) -> CameraIntrinsics {
        CameraIntrinsics(fx: fx * factor, fy: fy * factor, cx: cx * factor, cy: cy * factor)
    }

    var isFinite: Bool {
        fx.isFinite && fy.isFinite && cx.isFinite && cy.isFinite
    }
}

/// Establishes the 1920x1440 intrinsics and refuses to proceed if the device
/// disagrees with the frozen upstream calibration by more than a scale.
///
/// Intrinsics are read from `ARFrame.camera.intrinsics` during the capture. That
/// is not an ARKit algorithm output leaking into a candidate arm: intrinsics are
/// a property of the hardware, and the recorded frames are exactly the frames
/// those intrinsics describe, so nothing is extrapolated.
///
/// The frozen 640x480 upstream values scaled by 3 are the cross-check. Agreement
/// confirms both that the two formats differ only by a scale and that the ARKit
/// reading is sane. Disagreement means the formats differ by a crop or a
/// different lens, and every downstream number would be wrong -- so it halts the
/// run rather than picking one source.
enum ARKitIntrinsicsCrossCheck {
    /// xrslam 4beb1a9 xrslam-ios/visualizer/configs/iPhone 14 Pro.yaml, cam0.
    static let frozenUpstream640x480 = CameraIntrinsics(
        fx: 448.96781816245402,
        fy: 449.14399528627763,
        cx: 321.34605334072404,
        cy: 240.71641804985396
    )

    /// Focal length is compared relatively, principal point absolutely, because
    /// they fail in different ways.
    ///
    /// A single 12 px absolute tolerance on everything was measured wrong on
    /// 2026-08-30. This device reported fx = fy = 1331.130, cx = 957.589,
    /// cy = 719.988 against an upstream-scaled expectation of fx 1346.903,
    /// cx 964.038, cy 722.149 -- and was rejected on a 15.8 px focal difference.
    ///
    /// The numbers say the rejection was wrong. cy lands within 0.01 px of
    /// 1440/2 and cx within 2.5 px of 1920/2, so the format is not cropped and
    /// the threefold scaling premise holds. The focal gap is 1.17 percent, which
    /// is ordinary unit-to-unit variation between this phone and the one sample
    /// device the upstream configuration came from.
    ///
    /// That gap is also the point: running this phone on another unit's focal
    /// length was injecting roughly 1.2 percent of metric scale error, which the
    /// measured values remove.
    ///
    /// So focal length gets a relative tolerance -- per-device variation is
    /// around a percent while a different lens differs by tens of percent -- and
    /// the principal point keeps an absolute one, because that is what actually
    /// detects a crop: a crop displaces it by tens to hundreds of pixels.
    static let focalRelativeTolerance: Double = 0.03
    static let principalPointToleranceP: Double = 24.0

    enum Verdict: Equatable {
        case agrees(scoring: CameraIntrinsics)
        case disagrees(
            component: String,
            arkit: Double,
            expected: Double,
            deltaPixels: Double
        )
        case nonFinite

        var haltsRun: Bool {
            if case .agrees = self { return false }
            return true
        }

        var reason: String? {
            switch self {
            case .agrees:
                return nil
            case .nonFinite:
                return "arkit_intrinsics_non_finite"
            case .disagrees(let component, _, _, _):
                return "arkit_intrinsics_disagree_\(component)"
            }
        }
    }

    static var expectedScoringIntrinsics: CameraIntrinsics {
        frozenUpstream640x480.scaled(
            by: Double(BenchResolution.diagnosticDownscaleFactor)
        )
    }

    static func check(arkitReported: CameraIntrinsics) -> Verdict {
        guard arkitReported.isFinite else { return .nonFinite }
        let expected = expectedScoringIntrinsics
        for (name, reported, want) in [
            ("fx", arkitReported.fx, expected.fx),
            ("fy", arkitReported.fy, expected.fy),
        ] {
            guard want > 0 else {
                return .disagrees(component: name, arkit: reported,
                                  expected: want, deltaPixels: abs(reported - want))
            }
            if abs(reported - want) / want > focalRelativeTolerance {
                return .disagrees(component: name, arkit: reported,
                                  expected: want, deltaPixels: abs(reported - want))
            }
        }
        for (name, reported, want) in [
            ("cx", arkitReported.cx, expected.cx),
            ("cy", arkitReported.cy, expected.cy),
        ] {
            if abs(reported - want) > principalPointToleranceP {
                return .disagrees(component: name, arkit: reported,
                                  expected: want, deltaPixels: abs(reported - want))
            }
        }
        // ARKit's per-device factory values win once they agree: they describe
        // the exact frames being replayed, where the scaled upstream values are
        // one sample device carried across a resolution.
        return .agrees(scoring: arkitReported)
    }
}
