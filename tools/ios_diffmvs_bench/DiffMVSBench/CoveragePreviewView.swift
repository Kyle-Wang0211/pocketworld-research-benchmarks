import SwiftUI
import ARKit
import SceneKit
import simd

// RealityScan-style "red/yellow/green coverage preview".
//
// Runs an ARWorldTrackingConfiguration session and, every rendered frame,
// reads ARFrame.rawFeaturePoints (the sparse SLAM map). Each feature point has
// a stable UInt64 identifier; we accumulate points across frames keyed by that
// identifier and count how many frames each identifier persists. That
// observation count is our confidence proxy:
//   red    (1-2 obs)  -> freshly seen, low confidence
//   yellow (3-5 obs)
//   green  (>=6 obs)  -> well-observed, confidently reconstructed
//
// Points are rendered as small spheres anchored at their world position over
// the live camera feed. Memory is capped (kMaxPoints); when exceeded we evict
// the lowest-observation points first.
//
// NOTE: rawFeaturePoints is only populated by world tracking (it is the
// sparse map ARKit builds for tracking), so ARWorldTrackingConfiguration is
// required. On unsupported devices we show a message instead of crashing.
//
// IMPORTANT (ARKit pitfall): ARSCNView installs ITSELF as the ARSession's
// delegate to drive camera-background rendering and POV updates. We must NOT
// reassign `session.delegate` to our own object or that rendering breaks. So
// instead of conforming to ARSessionDelegate, we read each frame from the
// ARSCNViewDelegate render-loop callback `renderer(_:updateAtTime:)`, which is
// the supported hook and runs on SceneKit's render thread (off the main
// thread) — exactly where scene-graph mutation belongs.

// MARK: - Tunables

private let kMaxPoints = 50_000          // memory cap on accumulated points
private let kSphereRadius: CGFloat = 0.006 // meters; small dots in world space
private let kEvictBatch = 2_000          // how many to drop when over cap
private let kHudMarker = "PWCOV|"        // stdout marker, matches PWSFM/PWBENCH style

// MARK: - Accumulated point model

private struct CoveragePoint {
    var position: simd_float3
    var observations: Int
    var node: SCNNode          // the rendered sphere
    var lastBucket: Int        // cached color bucket (0=red,1=yellow,2=green)
}

// Observation count -> color bucket. 1-2 red, 3-5 yellow, >=6 green.
private func bucket(for obs: Int) -> Int {
    if obs >= 6 { return 2 }
    if obs >= 3 { return 1 }
    return 0
}

private func color(for b: Int) -> UIColor {
    switch b {
    case 2:  return UIColor.systemGreen
    case 1:  return UIColor.systemYellow
    default: return UIColor.systemRed
    }
}

private func trackingDescription(_ state: ARCamera.TrackingState) -> String {
    switch state {
    case .normal:                          return "normal"
    case .notAvailable:                    return "not available"
    case .limited(.excessiveMotion):       return "limited: slow down"
    case .limited(.insufficientFeatures):  return "limited: low texture"
    case .limited(.initializing):          return "initializing"
    case .limited(.relocalizing):          return "relocalizing"
    case .limited:                         return "limited"
    }
}

// MARK: - AR coordinator (owns the session + the accumulation map)

final class CoverageCoordinator: NSObject, ARSCNViewDelegate, ObservableObject {

    weak var sceneView: ARSCNView?

    // identifier (UInt64) -> accumulated point. The identifier is stable across
    // frames for a given tracked feature, which is what lets us count persistence.
    private var points: [UInt64: CoveragePoint] = [:]

    // One shared geometry per color bucket; spheres only swap their geometry
    // reference when their bucket changes, so we avoid per-frame material churn.
    private let bucketGeometry: [SCNSphere] = {
        (0..<3).map { b -> SCNSphere in
            let s = SCNSphere(radius: kSphereRadius)
            s.segmentCount = 6
            let m = SCNMaterial()
            m.diffuse.contents = color(for: b)
            m.lightingModel = .constant   // unlit: visible regardless of scene lighting
            s.firstMaterial = m
            return s
        }
    }()

    private let root = SCNNode()

    // Published HUD counters (read on main thread by SwiftUI).
    @Published var totalPoints = 0
    @Published var redCount = 0
    @Published var yellowCount = 0
    @Published var greenCount = 0
    @Published var trackingState = "starting"
    @Published var supported = ARWorldTrackingConfiguration.isSupported

    private var frameCounter = 0
    private var lastTrackingState = ""

    func attach(to view: ARSCNView) {
        sceneView = view
        view.scene.rootNode.addChildNode(root)
        // Only the ARSCNViewDelegate (render loop). Do NOT set session.delegate
        // — ARSCNView owns that and relies on it for camera-background rendering.
        view.delegate = self
        view.automaticallyUpdatesLighting = true
    }

    func start() {
        guard ARWorldTrackingConfiguration.isSupported, let view = sceneView else {
            print("\(kHudMarker) world tracking NOT supported on this device")
            return
        }
        let cfg = ARWorldTrackingConfiguration()
        cfg.worldAlignment = .gravity
        cfg.environmentTexturing = .none
        cfg.planeDetection = []           // we only need the sparse feature map
        view.session.run(cfg, options: [.resetTracking, .removeExistingAnchors])
        print("\(kHudMarker) session started (ARWorldTrackingConfiguration)")
    }

    func pause() {
        sceneView?.session.pause()
    }

    func reset() {
        for p in points.values { p.node.removeFromParentNode() }
        points.removeAll(keepingCapacity: true)
        frameCounter = 0
        publishCounts(force: true)
        start()
    }

    // MARK: ARSCNViewDelegate render loop
    //
    // Called once per rendered frame on SceneKit's render thread. We pull the
    // current ARFrame from the session (ARSCNView keeps it current) and ingest
    // its sparse feature map. Scene-graph mutation here is supported.

    func renderer(_ renderer: SCNSceneRenderer, updateAtTime time: TimeInterval) {
        guard let frame = sceneView?.session.currentFrame else { return }
        frameCounter += 1

        let stateStr = trackingDescription(frame.camera.trackingState)
        if stateStr != lastTrackingState {
            lastTrackingState = stateStr
            DispatchQueue.main.async { self.trackingState = stateStr }
        }

        ingest(frame.rawFeaturePoints)
    }

    // MARK: Accumulation

    private func ingest(_ cloud: ARPointCloud?) {
        guard let cloud = cloud else { return }
        let positions = cloud.points         // [simd_float3], world space
        let ids = cloud.identifiers          // [UInt64], parallel array

        let n = min(positions.count, ids.count)
        guard n > 0 else { return }

        for i in 0..<n {
            let id = ids[i]
            let pos = positions[i]
            if var existing = points[id] {
                // Seen before: bump observation count, refine position slightly.
                existing.observations += 1
                existing.position = pos
                existing.node.simdPosition = pos
                let b = bucket(for: existing.observations)
                if b != existing.lastBucket {
                    existing.node.geometry = bucketGeometry[b]
                    existing.lastBucket = b
                }
                points[id] = existing
            } else {
                // First sighting -> red, obs = 1.
                let node = SCNNode(geometry: bucketGeometry[0])
                node.simdPosition = pos
                root.addChildNode(node)
                points[id] = CoveragePoint(position: pos,
                                           observations: 1,
                                           node: node,
                                           lastBucket: 0)
            }
        }

        if points.count > kMaxPoints { evict() }

        // Throttle HUD/stdout updates to ~ every 10 frames to avoid spamming.
        if frameCounter % 10 == 0 { publishCounts(force: false) }
    }

    // Drop the lowest-observation points (least confident) when over the cap.
    private func evict() {
        let overflow = points.count - kMaxPoints + kEvictBatch
        guard overflow > 0 else { return }
        // Partial selection: sort ids by observation count ascending, take the
        // weakest `overflow`. kEvictBatch hysteresis keeps this from running
        // every single frame once we are at the cap.
        let victims = points
            .sorted { $0.value.observations < $1.value.observations }
            .prefix(overflow)
        for (id, p) in victims {
            p.node.removeFromParentNode()
            points.removeValue(forKey: id)
        }
    }

    private func publishCounts(force: Bool) {
        var r = 0, y = 0, g = 0
        for p in points.values {
            switch bucket(for: p.observations) {
            case 2: g += 1
            case 1: y += 1
            default: r += 1
            }
        }
        let total = points.count
        let track = lastTrackingState
        DispatchQueue.main.async {
            self.totalPoints = total
            self.redCount = r
            self.yellowCount = y
            self.greenCount = g
        }
        if force || frameCounter % 30 == 0 {
            print(String(format: "%@ frame=%d total=%d red=%d yellow=%d green=%d track=%@",
                         kHudMarker, frameCounter, total, r, y, g, track))
        }
    }
}

// MARK: - UIViewRepresentable wrapper for ARSCNView

struct CoverageARViewContainer: UIViewRepresentable {
    let coordinator: CoverageCoordinator

    func makeUIView(context: Context) -> ARSCNView {
        let view = ARSCNView(frame: .zero)
        view.automaticallyUpdatesLighting = true
        view.scene = SCNScene()
        coordinator.attach(to: view)
        coordinator.start()
        return view
    }

    func updateUIView(_ uiView: ARSCNView, context: Context) {}

    static func dismantleUIView(_ uiView: ARSCNView, coordinator: Void) {
        uiView.session.pause()
    }
}

// MARK: - SwiftUI screen

struct CoveragePreviewView: View {
    @StateObject private var coord = CoverageCoordinator()

    var body: some View {
        ZStack(alignment: .top) {
            if coord.supported {
                CoverageARViewContainer(coordinator: coord)
                    .edgesIgnoringSafeArea(.all)
            } else {
                Color.black.edgesIgnoringSafeArea(.all)
                Text("世界追踪不支持本设备\n(ARWorldTrackingConfiguration unavailable)")
                    .multilineTextAlignment(.center)
                    .foregroundColor(.white)
                    .padding()
            }

            VStack(spacing: 8) {
                HStack(spacing: 14) {
                    legend(.red,    "1-2", coord.redCount)
                    legend(.yellow, "3-5", coord.yellowCount)
                    legend(.green,  "≥6",  coord.greenCount)
                }
                HStack {
                    Text("点数 \(coord.totalPoints) / \(kMaxPoints)")
                    Spacer()
                    Text(coord.trackingState)
                }
                .font(.caption.monospacedDigit())
                .foregroundColor(.white)
            }
            .padding(10)
            .background(.black.opacity(0.45))
            .cornerRadius(12)
            .padding(.horizontal, 12)
            .padding(.top, 8)
        }
        .navigationTitle("覆盖预览")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button("重置") { coord.reset() }
            }
        }
        .onDisappear { coord.pause() }
    }

    private func legend(_ c: Color, _ label: String, _ n: Int) -> some View {
        HStack(spacing: 5) {
            Circle().fill(c).frame(width: 12, height: 12)
            Text("\(label): \(n)")
                .font(.caption.monospacedDigit())
                .foregroundColor(.white)
        }
    }
}
