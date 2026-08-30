
extension BenchSelfTestTests {
    /// The purge destroyed an operator's hand-shot 30 s capture because it
    /// deleted every run directory. An unmarked directory must survive it.
    func testPurgeSpareseUnmarkedOperatorRuns() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("purge-\(UUID().uuidString)/VIOBenchRuns")
        let operatorRun = root.appendingPathComponent("run-operator")
        let selfTestRun = root.appendingPathComponent("run-selftest")
        try FileManager.default.createDirectory(at: operatorRun, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: selfTestRun, withIntermediateDirectories: true)
        try Data().write(
            to: selfTestRun.appendingPathComponent(BenchSelfTest.selfTestMarkerName)
        )

        let removed = BenchSelfTest.purgeRuns(rootURL: root)

        XCTAssertEqual(removed, 1)
        XCTAssertTrue(FileManager.default.fileExists(atPath: operatorRun.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: selfTestRun.path))
    }
}
