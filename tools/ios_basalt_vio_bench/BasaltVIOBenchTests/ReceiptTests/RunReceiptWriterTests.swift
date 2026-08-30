import Foundation
import XCTest
@testable import VIOReplacementBench

final class RunReceiptWriterTests: XCTestCase {
    func testStartedTransitionsToEveryTerminalStateButTerminalCannotBeRewritten() throws {
        let started = makeReceipt()
        for state in RunReceiptState.terminalStates {
            var terminal = started
            terminal.state = state
            terminal.endedAtUTC = "2026-08-29T10:15:00.000Z"
            terminal.termination = RunTermination(
                reasonCode: reason(for: state),
                recoveredFromInterruption: false
            )
            if state == .validPass || state == .validFail {
                terminal.metrics = validLiveMetrics
            }
            XCTAssertNoThrow(try RunReceiptStateMachine.validateTransition(from: started, to: terminal))
        }

        var passed = started
        passed.state = .validPass
        passed.endedAtUTC = "2026-08-29T10:15:00.000Z"
        passed.termination = RunTermination(reasonCode: "thresholds_met", recoveredFromInterruption: false)
        passed.metrics = validLiveMetrics
        var rewritten = passed
        rewritten.state = .validFail
        rewritten.termination = RunTermination(reasonCode: "gates_not_met", recoveredFromInterruption: false)
        XCTAssertThrowsError(try RunReceiptStateMachine.validateTransition(from: passed, to: rewritten))
    }

    func testModelRejectsARKitProductionBundleFabricatedPowerAndMissingHashes() {
        var document = makeReceipt()
        document.app.usesARKit = true
        XCTAssertThrowsError(try document.validate())

        document = makeReceipt()
        document.app.bundleID = "com.kyle.PocketWorld"
        XCTAssertThrowsError(try document.validate())

        document = makeReceipt()
        document.power.powerW = 2.7
        XCTAssertThrowsError(try document.validate())

        document = makeReceipt()
        document.identities.configSHA256 = "deadbeef"
        XCTAssertThrowsError(try document.validate())
    }

    func testInterruptedStartedReceiptRecoversAtomicallyAsAborted() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("receipt-recovery-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let writer = RunReceiptWriter(directoryURL: directory, callbackQueue: .global())
        let startedWritten = expectation(description: "started receipt written")
        writer.enqueueStarted(makeReceipt()) { result in
            if case .failure(let error) = result {
                XCTFail("started write failed: \(error)")
            }
            startedWritten.fulfill()
        }
        wait(for: [startedWritten], timeout: 2)

        let recovered = expectation(description: "interrupted receipt recovered")
        writer.enqueueInterruptedRecovery(endedAtUTC: "2026-08-29T10:00:05.000Z") { result in
            do {
                let receipt = try XCTUnwrap(result.get())
                XCTAssertEqual(receipt.state, .aborted)
                XCTAssertEqual(receipt.termination?.reasonCode, "interrupted_recovery")
                XCTAssertEqual(receipt.termination?.recoveredFromInterruption, true)
            } catch {
                XCTFail("recovery failed: \(error)")
            }
            recovered.fulfill()
        }
        wait(for: [recovered], timeout: 2)

        let data = try Data(contentsOf: directory.appendingPathComponent("receipt.json"))
        let receipt = try RunReceiptJSON.decoder.decode(RunReceipt.self, from: data)
        XCTAssertEqual(receipt.state, .aborted)
        XCTAssertNoThrow(try receipt.validate())
    }

    func testLaunchRecoveryFindsStartedRunAndFinalizesEvidence() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("recovery-root-\(UUID().uuidString)", isDirectory: true)
        let directory = root.appendingPathComponent("run-test", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try Data("input".utf8).write(to: directory.appendingPathComponent("input_manifest.json"))
        try Data().write(to: directory.appendingPathComponent("telemetry.jsonl"))

        let writer = RunReceiptWriter(directoryURL: directory, callbackQueue: .global())
        let written = expectation(description: "started")
        var started = makeReceipt()
        started.startedAtUTC = BenchmarkRunPreparation.utcTimestamp()
        writer.enqueueStarted(started) { result in
            if case .failure(let error) = result {
                XCTFail("started write failed: \(error)")
            }
            written.fulfill()
        }
        wait(for: [written], timeout: 2)

        XCTAssertEqual(try InterruptedRunRecovery.recoverAll(rootURL: root), [directory])
        let recovered = try RunReceiptJSON.decoder.decode(
            RunReceipt.self,
            from: Data(contentsOf: directory.appendingPathComponent("receipt.json"))
        )
        XCTAssertEqual(recovered.state, .aborted)
        XCTAssertEqual(recovered.termination?.reasonCode, "interrupted_recovery")
        for name in ["heartbeat.json", "diagnostics.json", "SHA256SUMS", "artifact_manifest.json"] {
            XCTAssertTrue(FileManager.default.fileExists(atPath: directory.appendingPathComponent(name).path))
        }
    }

    func testSensorFacingHeartbeatEnqueueNeverWaitsForDisk() {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("receipt-nonblocking-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let startedData = try! RunReceiptJSON.encoder.encode(makeReceipt())
        try! FoundationAtomicDataWriter().writeAtomically(
            startedData,
            to: directory.appendingPathComponent("receipt.json")
        )
        let enteredSink = expectation(description: "background writer entered sink")
        let releaseSink = DispatchSemaphore(value: 0)
        let sink = BlockingAtomicDataWriter(entered: enteredSink, release: releaseSink)
        let writer = RunReceiptWriter(
            directoryURL: directory,
            callbackQueue: .global(),
            atomicWriter: sink
        )

        let start = CFAbsoluteTimeGetCurrent()
        writer.enqueueHeartbeat(
            RunHeartbeat(
                runID: makeReceipt().runID,
                sequence: 1,
                monotonicNS: 123,
                writtenAtUTC: "2026-08-29T10:00:01.000Z",
                startedReceiptSHA256: RunReceiptHash.sha256Hex(startedData)
            )
        ) { _ in }
        let elapsed = CFAbsoluteTimeGetCurrent() - start

        XCTAssertLessThan(elapsed, 0.05, "enqueue must not perform synchronous file I/O")
        wait(for: [enteredSink], timeout: 1)
        releaseSink.signal()
    }

    private var validLiveMetrics: [String: Double] {
        [
            "first_usable_pose_latency_ms": 420,
            "processed_fps": 29.5,
            "p95_pipeline_latency_ms": 48,
            "app_drop_rate": 0.002,
            "thermal_critical_seconds": 0,
            "thermal_serious_seconds": 0,
            "peak_phys_footprint_mb": 410,
            "finite_pose_ratio": 1,
            "battery_level_delta": -0.08,
            "cpu_seconds": 620,
        ]
    }

    private func makeReceipt() -> RunReceipt {
        RunReceipt(
            runID: "d94f40fc-2c5d-4fa6-a936-8f789d752f64",
            state: .started,
            channel: .liveSoak,
            inputCameraCount: 1,
            startedAtUTC: "2026-08-29T10:00:00.000Z",
            app: RunAppIdentity(
                bundleID: "com.kyle.viobench",
                usesARKit: false,
                backend: "cpu",
                algorithmMode: BenchBackend.basalt.algorithmMode,
                engineID: BenchBackend.basalt.id,
                upstreamRevision: BenchBackend.basalt.upstreamRevision,
                openCVVersion: BenchBackend.basalt.openCVVersion
            ),
            device: RunDeviceEvidence(
                modelIdentifier: "iPhone15,2",
                operatingSystemVersion: "Version 26.0 (Build 23A000)"
            ),
            identities: RunSHA256Identities(
                contractSHA256: String(repeating: "a", count: 64),
                appBinarySHA256: String(repeating: "b", count: 64),
                engineArtifactSHA256: String(repeating: "f", count: 64),
                configSHA256: String(repeating: "c", count: 64),
                inputDefinitionSHA256: String(repeating: "d", count: 64),
                metricDefinitionsSHA256: String(repeating: "e", count: 64)
            ),
            power: RunPowerEvidence(),
            accuracy: RunAccuracyEvidence(status: .notEvaluable, groundTruth: .none)
        )
    }

    func testCameraCountIsExplicitAndImmutable() throws {
        var live = makeReceipt()
        live.inputCameraCount = 2
        XCTAssertThrowsError(try live.validate())

        var replay = makeReceipt()
        replay.channel = .replayPaced
        replay.inputCameraCount = 2
        replay.accuracy = RunAccuracyEvidence(status: .evaluable, groundTruth: .euroc)
        XCTAssertNoThrow(try replay.validate())

        var terminal = makeReceipt()
        terminal.state = .aborted
        terminal.inputCameraCount = 2
        terminal.endedAtUTC = "2026-08-29T10:00:01.000Z"
        terminal.termination = RunTermination(reasonCode: "user_abort", recoveredFromInterruption: false)
        XCTAssertThrowsError(try RunReceiptStateMachine.validateTransition(from: makeReceipt(), to: terminal))
    }

    private func reason(for state: RunReceiptState) -> String {
        switch state {
        case .validPass: return "thresholds_met"
        case .validFail: return "gates_not_met"
        case .invalid: return "capture_interruption"
        case .aborted: return "user_abort"
        case .started: return ""
        }
    }
}

private final class BlockingAtomicDataWriter: AtomicDataWriting {
    private let entered: XCTestExpectation
    private let release: DispatchSemaphore

    init(entered: XCTestExpectation, release: DispatchSemaphore) {
        self.entered = entered
        self.release = release
    }

    func writeAtomically(_ data: Data, to destinationURL: URL) throws {
        entered.fulfill()
        _ = release.wait(timeout: .now() + 2)
    }
}
