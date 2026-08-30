import ARKit
import SwiftUI
import UIKit

/// What the operator is shown while a run is in progress.
///
/// An operator who cannot see the viewfinder cannot execute a real capture
/// trajectory, which is why `preview_enabled` moved to true. But the preview is
/// a consumer of frames the run already produced -- never a second camera
/// session, never an extra per-frame copy on the sensor path, and never an owner
/// of camera lifecycle. The coordinator's state machine remains the only thing
/// that starts and stops capture.
enum BenchPreviewSource: Equatable {
    /// The ARKit arm and the recording capture both draw the ARSession's own
    /// camera background. Opening an AVCaptureSession alongside it would be
    /// rejected by iOS anyway: the rear camera belongs to one session.
    case arSession(ARSession)

    /// Replay arms show the frame currently being replayed, so what the operator
    /// sees is literally what the algorithm is consuming.
    case replayedFrame

    /// Modes with nothing to show yet.
    case none

    static func == (lhs: BenchPreviewSource, rhs: BenchPreviewSource) -> Bool {
        switch (lhs, rhs) {
        case (.none, .none), (.replayedFrame, .replayedFrame):
            return true
        case (.arSession(let a), .arSession(let b)):
            return a === b
        default:
            return false
        }
    }

    var receiptMode: String {
        switch self {
        case .arSession: return "arsession_camera_background"
        case .replayedFrame: return "replayed_frame_passthrough"
        case .none: return "none"
        }
    }

    /// True only when this source displays frames the run already produced,
    /// without opening a capture session of its own. Every case must satisfy
    /// this; the property exists so a future case cannot quietly fail to.
    var isDisplayOnly: Bool {
        switch self {
        case .arSession, .replayedFrame, .none: return true
        }
    }
}

/// Renders the live ARSession's camera background.
///
/// `ARSCNView` is attached to the session the coordinator already owns; it does
/// not construct or configure one, and it never calls `run` or `pause`.
struct ARSessionPreview: UIViewRepresentable {
    let session: ARSession

    func makeUIView(context: Context) -> ARSCNView {
        let view = ARSCNView(frame: .zero)
        view.session = session
        // Display only: no scene content, no plane visualisation, no extra
        // per-frame work beyond drawing the background ARKit already decoded.
        view.automaticallyUpdatesLighting = false
        view.rendersContinuously = false
        view.scene = SCNScene()
        return view
    }

    func updateUIView(_ view: ARSCNView, context: Context) {
        if view.session !== session { view.session = session }
    }

    static func dismantleUIView(_ view: ARSCNView, coordinator: ()) {
        // Detach without pausing: the run, not the view, owns the session.
        view.session = ARSession()
    }
}

/// Renders the frame a replay run is currently feeding the engine.
///
/// The image is handed over after the engine has accepted the frame, so drawing
/// it cannot delay admission or change what the algorithm sees.
struct ReplayFramePreview: View {
    let image: CGImage?

    var body: some View {
        ZStack {
            Color.black
            if let image {
                Image(decorative: image, scale: 1, orientation: .up)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            } else {
                Text("等待回放帧")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

/// The preview area, sized to the scoring aspect ratio so the operator frames
/// the capture the way the algorithm will see it.
struct BenchPreview: View {
    let source: BenchPreviewSource
    let replayedFrame: CGImage?

    var body: some View {
        Group {
            switch source {
            case .arSession(let session):
                ARSessionPreview(session: session)
            case .replayedFrame:
                ReplayFramePreview(image: replayedFrame)
            case .none:
                ZStack {
                    Color.black
                    Text("未运行")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .aspectRatio(
            CGFloat(BenchResolution.scoring.width)
                / CGFloat(BenchResolution.scoring.height),
            contentMode: .fit
        )
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
