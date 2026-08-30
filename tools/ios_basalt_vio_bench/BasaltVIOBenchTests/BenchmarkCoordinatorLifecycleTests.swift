import Foundation
import XCTest
@testable import VIOReplacementBench

final class BenchmarkCoordinatorLifecycleTests: XCTestCase {
    func testEveryTerminalPathReleasesTheNativeSession() throws {
        let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsDirectory
            .deletingLastPathComponent()
            .appendingPathComponent("BasaltVIOBench/BenchmarkCoordinator.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)
        XCTAssertTrue(
            source.contains("session.close()\n                lock.withLock { activeSession = nil }"),
            "abort, invalid, and success paths must all release the only native session"
        )
    }

    func testNativeHandleClosesBeforeSuccessfulLeaseHandoff() throws {
        let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsDirectory
            .deletingLastPathComponent()
            .appendingPathComponent("BasaltVIOBench/BenchmarkCoordinator.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)
        let handoff = "session.close()\n        lock.withLock { activeSession = nil }\n        let exclusivity = runLease.release()"
        XCTAssertEqual(
            source.components(separatedBy: handoff).count - 1,
            2,
            "live and replay must destroy their native handle before lease release"
        )
    }

    func testNativeWrappersCloseIdempotentlyBeforeCallingBridgeDestroy() throws {
        let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let root = testsDirectory.deletingLastPathComponent()
        for relativePath in [
            "BasaltVIOBench/BasaltNativeSession.swift",
            "BasaltVIOBench/XRSLAMNativeSession.swift",
        ] {
            let source = try String(
                contentsOf: root.appendingPathComponent(relativePath),
                encoding: .utf8
            )
            XCTAssertTrue(source.contains("guard let handle else { return }"))
            let nilHandle = try XCTUnwrap(source.range(of: "self.handle = nil"))
            let destroy = try XCTUnwrap(source.range(of: "_bench_destroy(handle)"))
            XCTAssertLessThan(nilHandle.lowerBound, destroy.lowerBound)
        }
    }

    func testReleaseConfigurationDisablesCoverageInstrumentation() throws {
        let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let projectURL = testsDirectory
            .deletingLastPathComponent()
            .appendingPathComponent("project.yml")
        let source = try String(contentsOf: projectURL, encoding: .utf8)
        XCTAssertTrue(source.contains("CLANG_ENABLE_CODE_COVERAGE: NO"))
        XCTAssertTrue(source.contains("GCC_GENERATE_TEST_COVERAGE_FILES: NO"))
        XCTAssertTrue(source.contains("GCC_INSTRUMENT_PROGRAM_FLOW_ARCS: NO"))
    }

    func testARKitUsesDedicatedPathAndCannotEnterNativeSession() throws {
        let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsDirectory
            .deletingLastPathComponent()
            .appendingPathComponent("BasaltVIOBench/BenchmarkCoordinator.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)
        XCTAssertTrue(source.contains("if backend == .arkit"))
        XCTAssertTrue(source.contains("runARKitReference"))

        let sessionURL = testsDirectory
            .deletingLastPathComponent()
            .appendingPathComponent("BasaltVIOBench/ActiveVIOEngineSession.swift")
        let sessionSource = try String(contentsOf: sessionURL, encoding: .utf8)
        XCTAssertTrue(sessionSource.contains("ARKit reference uses its isolated ARSession adapter"))
    }

    func testLiveMeasurementStartsBeforeSelectedEstimatorInitialization() throws {
        let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sourceURL = testsDirectory
            .deletingLastPathComponent()
            .appendingPathComponent("BasaltVIOBench/BenchmarkCoordinator.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)

        let liveStart = try XCTUnwrap(
            source.range(of: "let liveRunStartNS = DispatchTime.now().uptimeNanoseconds")
        )
        let liveFunction = try XCTUnwrap(source.range(of: "private func runLive("))
        let liveFunctionEnd = try XCTUnwrap(source.range(of: "private func runReplay("))
        let liveBody = source[liveFunction.lowerBound..<liveFunctionEnd.lowerBound]
        let samplerStart = try XCTUnwrap(liveBody.range(of: "sampler.start()"))
        let engineCreation = try XCTUnwrap(
            liveBody.range(of: "let session = try ActiveVIOEngineSession(")
        )
        XCTAssertLessThan(liveStart.lowerBound, liveFunction.lowerBound)
        XCTAssertLessThan(samplerStart.lowerBound, engineCreation.lowerBound)

        let arFunction = try XCTUnwrap(source.range(of: "private func runARKitReference("))
        let arFunctionEnd = try XCTUnwrap(source.range(of: "private func runLive("))
        let arBody = source[arFunction.lowerBound..<arFunctionEnd.lowerBound]
        let arSamplerStart = try XCTUnwrap(arBody.range(of: "sampler.start()"))
        let arCPUStart = try XCTUnwrap(
            arBody.range(of: "let measurementCPUStart = SystemMetricSampler.processCPUSeconds().total")
        )
        let arSessionCreation = try XCTUnwrap(
            arBody.range(of: "let reference = ARKitReferenceSession(")
        )
        XCTAssertLessThan(arSamplerStart.lowerBound, arSessionCreation.lowerBound)
        XCTAssertLessThan(arCPUStart.lowerBound, arSessionCreation.lowerBound)
    }
}
