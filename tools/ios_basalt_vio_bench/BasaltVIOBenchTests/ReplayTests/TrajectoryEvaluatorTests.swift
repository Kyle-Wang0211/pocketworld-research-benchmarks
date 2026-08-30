import XCTest
@testable import VIOReplacementBench

final class TrajectoryEvaluatorTests: XCTestCase {
    private let evaluator = TrajectoryEvaluator(
        configuration: .init(
            associationToleranceNanoseconds: 0,
            minimumGroundTruthCoverage: 0.99,
            rpeHorizonNanoseconds: 1_000_000_000,
            rpeHorizonToleranceNanoseconds: 0
        )
    )

    func testFrozenProductionEvaluationDefaults() {
        let configuration = TrajectoryEvaluationConfiguration()
        XCTAssertEqual(configuration.associationToleranceNanoseconds, 5_000_000)
        XCTAssertEqual(configuration.minimumGroundTruthCoverage, 0.99)
        XCTAssertEqual(configuration.rpeHorizonNanoseconds, 1_000_000_000)
        XCTAssertEqual(configuration.rpeHorizonToleranceNanoseconds, 20_000_000)
    }

    func testGlobalRigidTransformAlignsToZeroWithoutChangingScale() throws {
        let identity = Quaternion.identity
        let global = Quaternion.angleAxis(radians: .pi / 2, axis: Vector3(x: 0, y: 0, z: 1))
        let offset = Vector3(x: 5, y: -3, z: 2)
        let groundTruth = [
            pose(0, 0, 0, 0, identity),
            pose(1, 1, 0, 0, identity),
            pose(2, 1, 1, 0, identity),
            pose(3, 2, 1, 1, identity),
        ]
        let estimated = groundTruth.map { sample in
            TimedPose(
                timestampNanoseconds: sample.timestampNanoseconds,
                translation: global.rotated(sample.translation) + offset,
                rotation: global * sample.rotation
            )
        }

        let result = try evaluator.evaluate(estimated: estimated, groundTruth: groundTruth)

        XCTAssertEqual(result.alignmentScale, 1.0)
        XCTAssertEqual(result.ateRMSEMeters, 0, accuracy: 1e-10)
        XCTAssertEqual(result.rpeTranslationRMSEMeters, 0, accuracy: 1e-10)
        XCTAssertEqual(result.rpeRotationRMSEDegrees, 0, accuracy: 1e-8)
    }

    func testFixedScaleTranslationDriftHasKnownATEAndOneSecondRPE() throws {
        let groundTruth = [pose(0, 0), pose(1, 1), pose(2, 2)]
        let estimated = [pose(0, 0), pose(1, 2), pose(2, 4)]

        let result = try evaluator.evaluate(estimated: estimated, groundTruth: groundTruth)

        XCTAssertEqual(result.alignmentScale, 1.0)
        XCTAssertEqual(result.ateRMSEMeters, sqrt(2.0 / 3.0), accuracy: 1e-10)
        XCTAssertEqual(result.rpeTranslationRMSEMeters, 1.0, accuracy: 1e-10)
        XCTAssertEqual(result.rpeRotationRMSEDegrees, 0, accuracy: 1e-10)
    }

    func testKnownTenDegreePerSecondRotationDrift() throws {
        let groundTruth = [pose(0, 0), pose(1, 0), pose(2, 0)]
        let estimated = (0...2).map { second in
            pose(
                Int64(second),
                0,
                0,
                0,
                Quaternion.angleAxis(
                    radians: Double(second) * 10.0 * .pi / 180.0,
                    axis: Vector3(x: 0, y: 0, z: 1)
                )
            )
        }

        let result = try evaluator.evaluate(estimated: estimated, groundTruth: groundTruth)

        XCTAssertEqual(result.ateRMSEMeters, 0, accuracy: 1e-10)
        XCTAssertEqual(result.rpeTranslationRMSEMeters, 0, accuracy: 1e-10)
        XCTAssertEqual(result.rpeRotationRMSEDegrees, 10, accuracy: 1e-8)
    }

    func testRejectsMissingGroundTruth() {
        XCTAssertThrowsError(try evaluator.evaluate(estimated: [pose(0, 0)], groundTruth: [])) { error in
            XCTAssertEqual(error as? TrajectoryEvaluationError, .missingGroundTruth)
        }
    }

    func testRejectsCoverageBelowNinetyNinePercent() {
        let estimated = (0..<100).map { pose(Int64($0), Double($0)) }
        let groundTruth = Array(estimated.prefix(98))

        XCTAssertThrowsError(try evaluator.evaluate(estimated: estimated, groundTruth: groundTruth)) { error in
            guard case .insufficientGroundTruthCoverage(let actual, let required) = error as? TrajectoryEvaluationError else {
                return XCTFail("unexpected error: \(error)")
            }
            XCTAssertEqual(actual, 0.98, accuracy: 1e-12)
            XCTAssertEqual(required, 0.99)
        }
    }

    func testAssociationTieUsesEarlierGroundTruthTimestampDeterministically() throws {
        let estimate = [TimedPose(timestampNanoseconds: 5, translation: .zero, rotation: .identity)]
        let groundTruth = [
            TimedPose(timestampNanoseconds: 0, translation: .zero, rotation: .identity),
            TimedPose(timestampNanoseconds: 10, translation: .zero, rotation: .identity),
        ]

        let matches = try TrajectoryAssociator.associate(
            estimated: estimate,
            groundTruth: groundTruth,
            toleranceNanoseconds: 5
        )

        XCTAssertEqual(matches.count, 1)
        XCTAssertEqual(matches[0].groundTruth.timestampNanoseconds, 0)
    }

    private func pose(
        _ seconds: Int64,
        _ x: Double,
        _ y: Double = 0,
        _ z: Double = 0,
        _ rotation: Quaternion = .identity
    ) -> TimedPose {
        TimedPose(
            timestampNanoseconds: seconds * 1_000_000_000,
            translation: Vector3(x: x, y: y, z: z),
            rotation: rotation
        )
    }
}
