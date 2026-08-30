import XCTest
@testable import VIOReplacementBench

final class GyroDrivenIMUAssemblerTests: XCTestCase {
    func testGyroTimestampDrivesLinearAccelerationInterpolation() {
        var assembler = GyroDrivenIMUAssembler(pendingGyroscopeCapacity: 8)
        let lower = vector(timestamp: 100, x: 1, y: 2, z: 3)
        let gyro = vector(timestamp: 125, x: 10, y: 20, z: 30)
        let upper = vector(timestamp: 200, x: 5, y: 10, z: 15)

        XCTAssertTrue(assembler.ingestAcceleration(lower).samples.isEmpty)
        XCTAssertTrue(assembler.ingestGyroscope(gyro).samples.isEmpty)
        let batch = assembler.ingestAcceleration(upper)

        XCTAssertNil(batch.violation)
        XCTAssertEqual(batch.samples.count, 1)
        let sample = try! XCTUnwrap(batch.samples.first)
        XCTAssertEqual(sample.timestampNanoseconds, gyro.timestampNanoseconds)
        XCTAssertEqual(sample.gyroscope, gyro)
        XCTAssertEqual(sample.acceleration.x, 2.0, accuracy: 1e-12)
        XCTAssertEqual(sample.acceleration.y, 4.0, accuracy: 1e-12)
        XCTAssertEqual(sample.acceleration.z, 6.0, accuracy: 1e-12)
        XCTAssertEqual(sample.accelerationLowerTimestampNanoseconds, 100)
        XCTAssertEqual(sample.accelerationUpperTimestampNanoseconds, 200)
    }

    func testMatchesOfficialStrictUpperBoundAndEmitsBoundaryGyroNextInterval() {
        var assembler = GyroDrivenIMUAssembler(pendingGyroscopeCapacity: 8)
        _ = assembler.ingestAcceleration(vector(timestamp: 100, x: 1))
        _ = assembler.ingestGyroscope(vector(timestamp: 200, x: 9))

        XCTAssertTrue(
            assembler.ingestAcceleration(vector(timestamp: 200, x: 2)).samples.isEmpty
        )
        let emitted = assembler.ingestAcceleration(vector(timestamp: 300, x: 3)).samples

        XCTAssertEqual(emitted.map(\.timestampNanoseconds), [200])
        XCTAssertEqual(emitted.first?.acceleration.x, 2)
    }

    func testEmitsMultipleGyrosInStrictTimestampOrder() {
        var assembler = GyroDrivenIMUAssembler(pendingGyroscopeCapacity: 8)
        _ = assembler.ingestAcceleration(vector(timestamp: 100, x: 0))
        _ = assembler.ingestGyroscope(vector(timestamp: 120, x: 1))
        _ = assembler.ingestGyroscope(vector(timestamp: 140, x: 2))
        _ = assembler.ingestGyroscope(vector(timestamp: 160, x: 3))

        let batch = assembler.ingestAcceleration(vector(timestamp: 200, x: 10))

        XCTAssertNil(batch.violation)
        XCTAssertEqual(batch.samples.map(\.timestampNanoseconds), [120, 140, 160])
        XCTAssertEqual(batch.samples.map(\.gyroscope.x), [1, 2, 3])
        XCTAssertEqual(batch.samples.map(\.acceleration.x), [2, 4, 6])
    }

    func testSkipsGyroBeforeFirstAccelerationAndReceiptsTheDrop() {
        var assembler = GyroDrivenIMUAssembler(pendingGyroscopeCapacity: 8)
        _ = assembler.ingestGyroscope(vector(timestamp: 90, x: 1))
        _ = assembler.ingestAcceleration(vector(timestamp: 100, x: 0))

        let batch = assembler.ingestAcceleration(vector(timestamp: 200, x: 2))

        XCTAssertTrue(batch.samples.isEmpty)
        XCTAssertEqual(batch.unbracketedGyroscopeDrops, 1)
        XCTAssertEqual(assembler.receipt.unbracketedGyroscopeDrops, 1)
    }

    func testRejectsTimestampRegressionsWithoutCorruptingOrderedState() {
        var assembler = GyroDrivenIMUAssembler(pendingGyroscopeCapacity: 8)
        _ = assembler.ingestGyroscope(vector(timestamp: 100))

        let gyroRegression = assembler.ingestGyroscope(vector(timestamp: 99))
        XCTAssertEqual(
            gyroRegression.violation,
            .gyroscopeTimestampRegression(previous: 100, received: 99)
        )

        _ = assembler.ingestAcceleration(vector(timestamp: 50))
        let accelRegression = assembler.ingestAcceleration(vector(timestamp: 50))
        XCTAssertEqual(
            accelRegression.violation,
            .accelerationTimestampRegression(previous: 50, received: 50)
        )

        XCTAssertEqual(assembler.receipt.gyroscopeTimestampRegressions, 1)
        XCTAssertEqual(assembler.receipt.accelerationTimestampRegressions, 1)
    }

    func testPendingGyroCapacityIsBoundedAndOverflowIsReceipted() {
        var assembler = GyroDrivenIMUAssembler(pendingGyroscopeCapacity: 2)
        XCTAssertNil(assembler.ingestGyroscope(vector(timestamp: 10)).violation)
        XCTAssertNil(assembler.ingestGyroscope(vector(timestamp: 20)).violation)

        let overflow = assembler.ingestGyroscope(vector(timestamp: 30))

        XCTAssertEqual(overflow.violation, .pendingGyroscopeOverflow(capacity: 2))
        XCTAssertEqual(assembler.receipt.pendingGyroscopeDepth, 2)
        XCTAssertEqual(assembler.receipt.pendingGyroscopeHighWatermark, 2)
        XCTAssertEqual(assembler.receipt.pendingGyroscopeOverflowDrops, 1)
    }

    func testSealAccountsPendingGyrosAndRejectsAllFutureInput() {
        var assembler = GyroDrivenIMUAssembler(pendingGyroscopeCapacity: 4)
        _ = assembler.ingestAcceleration(vector(timestamp: 100))
        _ = assembler.ingestGyroscope(vector(timestamp: 150))
        _ = assembler.ingestGyroscope(vector(timestamp: 200))

        XCTAssertEqual(assembler.seal(), .sealed)
        XCTAssertEqual(assembler.seal(), .sealed)
        XCTAssertEqual(assembler.receipt.sealedPendingGyroscopeDrops, 2)
        XCTAssertEqual(assembler.receipt.pendingGyroscopeDepth, 0)

        XCTAssertEqual(
            assembler.ingestGyroscope(vector(timestamp: 300)).violation,
            .inputSealed
        )
        XCTAssertEqual(
            assembler.ingestAcceleration(vector(timestamp: 300)).violation,
            .inputSealed
        )
        XCTAssertEqual(assembler.receipt.sealedInputRejections, 2)
    }

    func testExpectedBoundaryDropsDoNotCountAsIntegrityLoss() {
        var assembler = GyroDrivenIMUAssembler(pendingGyroscopeCapacity: 8)
        _ = assembler.ingestGyroscope(vector(timestamp: 90))
        _ = assembler.ingestAcceleration(vector(timestamp: 100))
        _ = assembler.ingestAcceleration(vector(timestamp: 200))
        _ = assembler.ingestGyroscope(vector(timestamp: 250))
        _ = assembler.seal()

        XCTAssertEqual(assembler.receipt.unbracketedGyroscopeDrops, 1)
        XCTAssertEqual(assembler.receipt.sealedPendingGyroscopeDrops, 1)
        XCTAssertEqual(assembler.receipt.integrityLossCount, 0)
    }

    private func vector(
        timestamp: UInt64,
        x: Double = 0,
        y: Double = 0,
        z: Double = 0
    ) -> MotionVectorSample {
        MotionVectorSample(timestampNanoseconds: timestamp, x: x, y: y, z: z)
    }
}
