import AVFoundation
import CoreGraphics
import Foundation
import UIKit

@MainActor
final class BenchViewModel: ObservableObject {
    @Published var selectedBackend: BenchBackend = .basalt
    @Published var mode: BenchMode = .liveSoak
    @Published private(set) var phase: BenchPhase = .idle
    @Published private(set) var snapshot = LiveSnapshot()
    @Published private(set) var blockingMessage: String?
    @Published private(set) var lastReceiptURL: URL?
    @Published var isImportingDataset = false

    /// Display-only. Publishing a preview source never starts or stops capture.
    @Published private(set) var previewSource: BenchPreviewSource = .none
    @Published private(set) var previewFrame: CGImage?

    private(set) var datasetURL: URL?
    private var coordinator: BenchmarkCoordinator?

    init() {
        Task.detached(priority: .utility) {
            _ = try? InterruptedRunRecovery.recoverAll()
        }
    }

    /// Mirrors the coordinator's guard so the UI cannot offer a run that will
    /// be refused. The coordinator stays authoritative.
    var modeBackendConflict: String? {
        mode == .record && selectedBackend != .arkit
            ? "录制模式由 ARKit 臂持有相机,请把引擎切到 ARKit"
            : nil
    }

    var isRunning: Bool {
        [.preparing, .warmup, .measuring, .draining].contains(phase)
    }

    var datasetLabel: String? { datasetURL?.lastPathComponent }

    var canStart: Bool {
        guard !isRunning, modeBackendConflict == nil else { return false }
        switch mode {
        case .record:
            // ARKit owns the camera and the recording is of its frames.
            return selectedBackend == .arkit
        case .liveSoak:
            return true
        case .replayDeviceRecording, .replayPaced, .replayMax:
            // ARKit cannot be fed a recording, and a replay needs one.
            return selectedBackend != .arkit && datasetURL != nil
        }
    }

    func requestDatasetImport() { isImportingDataset = true }

    func acceptDatasetImport(_ result: Result<[URL], Error>) {
        do {
            datasetURL = try result.get().first
            blockingMessage = nil
            objectWillChange.send()
        } catch {
            blockingMessage = "数据集选择失败：\(error.localizedDescription)"
        }
    }

    func start() {
        guard canStart else { return }
        if mode == .liveSoak,
           let reason = LiveCalibrationGate.rejectionReason(for: .current()) {
            blockingMessage = reason
            phase = .failed
            return
        }
        if mode == .liveSoak {
            switch AVCaptureDevice.authorizationStatus(for: .video) {
            case .authorized:
                break
            case .notDetermined:
                blockingMessage = nil
                phase = .preparing
                AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                    Task { @MainActor in
                        guard let self else { return }
                        if granted {
                            self.startAuthorizedRun()
                        } else {
                            self.blockingMessage = "相机权限被拒绝，实时 \(self.selectedBackend.displayName) bench 无法运行。"
                            self.phase = .failed
                        }
                    }
                }
                return
            default:
                blockingMessage = "相机权限不可用，实时 \(selectedBackend.displayName) bench 无法运行。"
                phase = .failed
                return
            }
        }
        startAuthorizedRun()
    }

    private func startAuthorizedRun() {
        blockingMessage = nil
        lastReceiptURL = nil
        snapshot = LiveSnapshot()
        phase = .preparing
        UIApplication.shared.isIdleTimerDisabled = true

        let coordinator = BenchmarkCoordinator(
            backend: selectedBackend,
            mode: mode,
            datasetURL: datasetURL,
            onPhase: { [weak self] phase in Task { @MainActor in self?.phase = phase } },
            onSnapshot: { [weak self] value in Task { @MainActor in self?.snapshot = value } },
            onPreview: { [weak self] source in
                Task { @MainActor in
                    self?.previewSource = source
                    if case .none = source { self?.previewFrame = nil }
                }
            },
            onPreviewFrame: { [weak self] image in
                Task { @MainActor in self?.previewFrame = image }
            },
            onFinish: { [weak self] result in
                Task { @MainActor in
                    UIApplication.shared.isIdleTimerDisabled = false
                    switch result {
                    case .success(let url):
                        self?.lastReceiptURL = url
                        self?.phase = .completed
                    case .failure(let error):
                        self?.blockingMessage = error.localizedDescription
                        self?.phase = .failed
                    }
                    self?.coordinator = nil
                }
            }
        )
        self.coordinator = coordinator
        coordinator.start()
    }

    func abort() {
        coordinator?.abort()
    }
}
