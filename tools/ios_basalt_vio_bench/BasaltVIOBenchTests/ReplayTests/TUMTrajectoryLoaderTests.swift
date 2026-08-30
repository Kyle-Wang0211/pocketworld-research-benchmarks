import Foundation
import XCTest
@testable import VIOReplacementBench

final class TUMTrajectoryLoaderTests: XCTestCase {
    func testLoadsExactNanosecondTimestampsAndTUMQuaternionOrder() throws {
        let url = try temporaryTrajectory(
            "1403636579.764355558 1 2 3 0 0 0 1\n"
                + "1403636580.000000001 4 5 6 0 0 0.7071067811865475 0.7071067811865476\n"
        )

        let poses = try TUMTrajectoryLoader().load(url: url)

        XCTAssertEqual(poses.map(\.timestampNanoseconds), [1_403_636_579_764_355_558, 1_403_636_580_000_000_001])
        XCTAssertEqual(poses[0].translation, Vector3(x: 1, y: 2, z: 3))
        XCTAssertEqual(poses[1].rotation.shortestAngleRadians, .pi / 2, accuracy: 1e-12)
    }

    func testRejectsPartialPoseRowInsteadOfDroppingIt() throws {
        let url = try temporaryTrajectory("0.0 0 0 0 0 0 0 1\n1.0 1 0\n")

        XCTAssertThrowsError(try TUMTrajectoryLoader().load(url: url)) { error in
            guard case .malformedLine(let line, _) = error as? TUMTrajectoryError else {
                return XCTFail("unexpected error: \(error)")
            }
            XCTAssertEqual(line, 2)
        }
    }

    func testRejectsSubNanosecondTimestampInsteadOfRounding() throws {
        let url = try temporaryTrajectory("0.0000000001 0 0 0 0 0 0 1\n")

        XCTAssertThrowsError(try TUMTrajectoryLoader().load(url: url)) { error in
            guard case .malformedLine(let line, _) = error as? TUMTrajectoryError else {
                return XCTFail("unexpected error: \(error)")
            }
            XCTAssertEqual(line, 1)
        }
    }

    private func temporaryTrajectory(_ contents: String) throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("poses-\(UUID().uuidString).tum")
        try Data(contents.utf8).write(to: url)
        addTeardownBlock { try? FileManager.default.removeItem(at: url) }
        return url
    }
}
