import Foundation
import XCTest
@testable import VIOReplacementBench

final class EuRoCReplayLoaderTests: XCTestCase {
    func testDatasetIdentityMatchesThePythonBuilderGoldenVector() throws {
        let manifest = EuRoCOrderedManifest(
            schemaVersion: 1,
            datasetName: "EuRoC_MH_01_easy",
            inputCameraCount: 1,
            datasetSHA256: "",
            files: [
                EuRoCManifestFile(
                    role: .camera0Index,
                    relativePath: "mav0/cam0/data.csv",
                    byteCount: 3,
                    sha256: String(repeating: "a", count: 64)
                ),
                EuRoCManifestFile(
                    role: .cameraImage,
                    relativePath: "mav0/cam0/data/0.png",
                    byteCount: 2,
                    sha256: String(repeating: "b", count: 64)
                ),
                EuRoCManifestFile(
                    role: .imuIndex,
                    relativePath: "mav0/imu0/data.csv",
                    byteCount: 4,
                    sha256: String(repeating: "c", count: 64)
                ),
            ]
        )
        XCTAssertEqual(
            try EuRoCDatasetIdentity.compute(
                rootURL: FileManager.default.temporaryDirectory,
                manifest: manifest
            ),
            "e2d4121a08633d4c3a04b8df01e50a330d3d41ce55085d48787932e9177d54cc"
        )
    }

    func testLoadsStrictlyOrderedStereoAndIMUAndVerifiesIdentity() throws {
        let fixture = try EuRoCTestFixture()
        let dataset = try EuRoCReplayLoader().load(manifestURL: fixture.manifestURL)

        XCTAssertEqual(dataset.datasetName, "synthetic_euroc")
        XCTAssertEqual(dataset.inputCameraCount, 2)
        XCTAssertEqual(dataset.datasetSHA256, fixture.manifest.datasetSHA256)
        XCTAssertEqual(dataset.events.map(\.timestampNanoseconds), [
            0, 0, 500_000_000, 1_000_000_000, 1_000_000_000, 1_500_000_000,
            2_000_000_000, 2_000_000_000,
        ])
        XCTAssertEqual(dataset.events.map(\.kind), [
            .imu, .camera, .imu, .imu, .camera, .imu, .imu, .camera,
        ])
        XCTAssertEqual(dataset.groundTruth.count, 3)
    }

    func testLoadsFrozenMonoCam0ManifestAndExposesReceiptCameraCount() throws {
        let fixture = try EuRoCTestFixture(inputCameraCount: 1)

        let dataset = try EuRoCReplayLoader().load(manifestURL: fixture.manifestURL)

        XCTAssertEqual(dataset.inputCameraCount, 1)
        let cameraFrames = dataset.events.compactMap { event -> EuRoCCameraFrame? in
            guard case .camera(let frame) = event else { return nil }
            return frame
        }
        XCTAssertEqual(cameraFrames.count, 3)
        XCTAssertTrue(cameraFrames.allSatisfy { $0.inputCameraCount == 1 && $0.camera1ImageURL == nil })
    }

    func testMonoManifestRejectsCam1RolesInsteadOfSilentlyUsingStereo() throws {
        let fixture = try EuRoCTestFixture(inputCameraCount: 2)
        try fixture.rewriteManifest { manifest in
            manifest.inputCameraCount = 1
        }

        XCTAssertThrowsError(try EuRoCReplayLoader().load(manifestURL: fixture.manifestURL)) { error in
            XCTAssertEqual(
                error as? EuRoCReplayError,
                .roleNotAllowedForInputCameraCount(role: .camera1Index, inputCameraCount: 1)
            )
        }
    }

    func testRejectsMissingGroundTruthRole() throws {
        let fixture = try EuRoCTestFixture()
        try fixture.rewriteManifest { manifest in
            manifest.files.removeAll { $0.role == .groundTruth }
        }

        XCTAssertThrowsError(try EuRoCReplayLoader().load(manifestURL: fixture.manifestURL)) { error in
            XCTAssertEqual(error as? EuRoCReplayError, .missingRequiredRole(.groundTruth))
        }
    }

    func testRejectsMalformedGroundTruthInsteadOfSilentlyDroppingRows() throws {
        let fixture = try EuRoCTestFixture()
        try fixture.replaceFile(
            relativePath: "mav0/state_groundtruth_estimate0/data.csv",
            contents: "#timestamp,p_RS_R_x,p_RS_R_y,p_RS_R_z,q_RS_w,q_RS_x,q_RS_y,q_RS_z\n0,0,0,0,1,0,0,0\n1000000000,1,0\n"
        )

        XCTAssertThrowsError(try EuRoCReplayLoader().load(manifestURL: fixture.manifestURL)) { error in
            guard case .malformedCSV(let path, let line, _) = error as? EuRoCReplayError else {
                return XCTFail("unexpected error: \(error)")
            }
            XCTAssertEqual(path, "mav0/state_groundtruth_estimate0/data.csv")
            XCTAssertEqual(line, 3)
        }
    }

    func testRejectsGroundTruthThatDoesNotCoverReplaySpan() throws {
        let fixture = try EuRoCTestFixture()
        try fixture.replaceFile(
            relativePath: "mav0/state_groundtruth_estimate0/data.csv",
            contents: "#timestamp,p_RS_R_x,p_RS_R_y,p_RS_R_z,q_RS_w,q_RS_x,q_RS_y,q_RS_z\n0,0,0,0,1,0,0,0\n1000000000,1,0,0,1,0,0,0\n"
        )

        XCTAssertThrowsError(try EuRoCReplayLoader().load(manifestURL: fixture.manifestURL)) { error in
            XCTAssertEqual(error as? EuRoCReplayError, .groundTruthDoesNotCoverReplay)
        }
    }

    func testDatasetIdentityChangesWhenPayloadChanges() throws {
        let fixture = try EuRoCTestFixture()
        let original = fixture.manifest.datasetSHA256
        try fixture.replaceFile(
            relativePath: "mav0/cam0/data/1000000000.png",
            data: Data([0x01, 0x02, 0x03])
        )

        XCTAssertNotEqual(fixture.manifest.datasetSHA256, original)
        let loaded = try EuRoCReplayLoader().load(manifestURL: fixture.manifestURL)
        XCTAssertEqual(loaded.datasetSHA256, fixture.manifest.datasetSHA256)
    }

    func testRejectsPayloadTamperingBeforeTrustingDatasetIdentity() throws {
        let fixture = try EuRoCTestFixture()
        let path = "mav0/cam0/data/1000000000.png"
        try Data([0xff]).write(to: fixture.rootURL.appendingPathComponent(path))

        XCTAssertThrowsError(try EuRoCReplayLoader().load(manifestURL: fixture.manifestURL)) { error in
            guard case .fileHashMismatch(let actualPath, _, _) = error as? EuRoCReplayError else {
                return XCTFail("unexpected error: \(error)")
            }
            XCTAssertEqual(actualPath, path)
        }
    }

    func testRejectsUnsortedManifestRatherThanCanonicalizingItSilently() throws {
        let fixture = try EuRoCTestFixture()
        try fixture.rewriteManifest(recomputeIdentity: false) { manifest in
            manifest.files.swapAt(0, 1)
        }

        XCTAssertThrowsError(try EuRoCReplayLoader().load(manifestURL: fixture.manifestURL)) { error in
            XCTAssertEqual(error as? EuRoCReplayError, .manifestFilesNotStrictlySorted)
        }
    }
}

private final class EuRoCTestFixture {
    let rootURL: URL
    let manifestURL: URL
    var manifest: EuRoCOrderedManifest

    init(inputCameraCount: Int = 2) throws {
        rootURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("euroc-replay-\(UUID().uuidString)", isDirectory: true)
        manifestURL = rootURL.appendingPathComponent("input_manifest.json")
        try FileManager.default.createDirectory(at: rootURL, withIntermediateDirectories: true)

        let allContents: [(EuRoCFileRole, String, Data)] = [
            (.camera0Calibration, "mav0/cam0/sensor.yaml", Data("sensor_type: camera\n".utf8)),
            (.camera0Index, "mav0/cam0/data.csv", Data("#timestamp,filename\n0,0.png\n1000000000,1000000000.png\n2000000000,2000000000.png\n".utf8)),
            (.cameraImage, "mav0/cam0/data/0.png", Data([0x00])),
            (.cameraImage, "mav0/cam0/data/1000000000.png", Data([0x01])),
            (.cameraImage, "mav0/cam0/data/2000000000.png", Data([0x02])),
            (.camera1Calibration, "mav0/cam1/sensor.yaml", Data("sensor_type: camera\n".utf8)),
            (.camera1Index, "mav0/cam1/data.csv", Data("#timestamp,filename\n0,0.png\n1000000000,1000000000.png\n2000000000,2000000000.png\n".utf8)),
            (.cameraImage, "mav0/cam1/data/0.png", Data([0x10])),
            (.cameraImage, "mav0/cam1/data/1000000000.png", Data([0x11])),
            (.cameraImage, "mav0/cam1/data/2000000000.png", Data([0x12])),
            (.imuCalibration, "mav0/imu0/sensor.yaml", Data("sensor_type: imu\n".utf8)),
            (.imuIndex, "mav0/imu0/data.csv", Data("#timestamp,w_x,w_y,w_z,a_x,a_y,a_z\n0,0,0,0,0,0,9.81\n500000000,0,0,0,0,0,9.81\n1000000000,0,0,0,0,0,9.81\n1500000000,0,0,0,0,0,9.81\n2000000000,0,0,0,0,0,9.81\n".utf8)),
            (.groundTruth, "mav0/state_groundtruth_estimate0/data.csv", Data("#timestamp,p_RS_R_x,p_RS_R_y,p_RS_R_z,q_RS_w,q_RS_x,q_RS_y,q_RS_z\n0,0,0,0,1,0,0,0\n1000000000,1,0,0,1,0,0,0\n2000000000,2,0,0,1,0,0,0\n".utf8)),
        ]
        let contents = allContents.filter { _, path, _ in
            inputCameraCount == 2 || !path.hasPrefix("mav0/cam1/")
        }

        for (_, path, data) in contents {
            let url = rootURL.appendingPathComponent(path)
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try data.write(to: url)
        }

        let files = contents.map { role, path, data in
            EuRoCManifestFile(
                role: role,
                relativePath: path,
                byteCount: Int64(data.count),
                sha256: EuRoCDatasetIdentity.sha256Hex(data)
            )
        }.sorted { $0.relativePath < $1.relativePath }
        manifest = EuRoCOrderedManifest(
            schemaVersion: 1,
            datasetName: "synthetic_euroc",
            inputCameraCount: inputCameraCount,
            datasetSHA256: "",
            files: files
        )
        manifest.datasetSHA256 = try EuRoCDatasetIdentity.compute(rootURL: rootURL, manifest: manifest)
        try writeManifest()
    }

    deinit {
        try? FileManager.default.removeItem(at: rootURL)
    }

    func rewriteManifest(
        recomputeIdentity: Bool = true,
        _ change: (inout EuRoCOrderedManifest) -> Void
    ) throws {
        change(&manifest)
        if recomputeIdentity {
            manifest.datasetSHA256 = try EuRoCDatasetIdentity.compute(rootURL: rootURL, manifest: manifest)
        }
        try writeManifest()
    }

    func replaceFile(relativePath: String, contents: String) throws {
        try replaceFile(relativePath: relativePath, data: Data(contents.utf8))
    }

    func replaceFile(relativePath: String, data: Data) throws {
        try data.write(to: rootURL.appendingPathComponent(relativePath))
        try rewriteManifest { manifest in
            let index = manifest.files.firstIndex { $0.relativePath == relativePath }!
            manifest.files[index].byteCount = Int64(data.count)
            manifest.files[index].sha256 = EuRoCDatasetIdentity.sha256Hex(data)
        }
    }

    private func writeManifest() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        try encoder.encode(manifest).write(to: manifestURL)
    }
}
