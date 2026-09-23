import io, sys, re
p = "/Users/kaidongwang/Developer/pocketworld-wt-photo/ios/Runner/PwCameraSlot.swift"
s = io.open(p, encoding="utf-8").read()
orig = s

# ── A. import ImageIO ────────────────────────────────────────────────────
a_old = "import AVFoundation\nimport CoreVideo\nimport Foundation\n"
a_new = "import AVFoundation\nimport CoreVideo\nimport Foundation\nimport ImageIO\n"
assert s.count(a_old) == 1, "A anchor"
s = s.replace(a_old, a_new)

# ── B. 存储属性 ──────────────────────────────────────────────────────────
b_old = """    fileprivate var device: AVCaptureDevice?
    fileprivate var pickedFormatIsBinned: Bool = false
"""
b_new = """    fileprivate var device: AVCaptureDevice?
    fileprivate var pickedFormatIsBinned: Bool = false

    // ── 高清拍照(见文件末尾 MARK: 高清拍照)────────────────────────────
    /// 最新一帧视频流的实际交付尺寸。**内参按分辨率缩放时的分母就是它**,
    /// 不能用 start() 传进来的请求值 —— 请求值不保证等于实际交付值。
    fileprivate var latestFrameWidth: Int = 0
    fileprivate var latestFrameHeight: Int = 0

    fileprivate var photoOutput: AVCapturePhotoOutput?
    /// 照片输出没装上时,原因原样记下来写进 sidecar,而不是静默降级。
    fileprivate var photoOutputNote: String = "not_installed"
    /// 采集配置完成、**startRunning 之前**拍下的视频档快照。拍照时再拍一张
    /// 与它比,就是"加照片输出没有降低视频流格式/帧率"的运行期自证。
    fileprivate var configuredVideoProof: [String: Any] = [:]

    private let photoLock = NSLock()
    /// 一次拍照一个 delegate 对象(抄 AVCam:`inProgressPhotoCaptureDelegates`,
    /// 因为"The Photo Output keeps a weak reference to the photo capture
    /// delegate so we store it in an array to maintain a strong reference"）。
    private var inFlightPhotos: [Int64: PwPhotoCaptureProcessor] = [:]
    /// 已完成、等待被 poll 取走的结果。**FIFO、有界**:拍得比取得快时丢最老的,
    /// 并把丢弃数计账 —— 不静默。
    private var completedPhotos: [PwPhotoResult] = []
    private var photoDropped: Int64 = 0
    private static let kCompletedPhotoCap = 32

    /// 文件落盘与 JSON 序列化都在这条队列上,**绝不占用 `queue`** ——
    /// `queue` 是相机帧与 IMU 共享的那条串行上下文(见上面 bindSerialQueue),
    /// 在它上面写几 MB 文件等于给 VIO 喂料插一根桩。
    fileprivate let photoQueue = DispatchQueue(
        label: "com.pocketworld.camera.photo", qos: .utility)
"""
assert s.count(b_old) == 1, "B anchor"
s = s.replace(b_old, b_new)

# ── C. start(): 装照片输出 ───────────────────────────────────────────────
c_old = """        guard s.canAddOutput(out) else { s.commitConfiguration(); return -5 }
        s.addOutput(out)
"""
c_new = """        guard s.canAddOutput(out) else { s.commitConfiguration(); return -5 }
        s.addOutput(out)

        // ── 照片输出(抄 AVCam `CameraViewController.configureSession()` 的
        //    "// Add photo output." 那一段:`canAddOutput` → `addOutput` →
        //    置高清相关开关)。
        //    🔴 **失败不影响视频流**:装不上就记原因、继续跑 VIO,
        //       只让 pw_camera_slot_capture_photo 返回错误码。
        //    🔴 位置是承重的:必须在 `beginConfiguration` 块内加输出,且必须
        //       在下面 `device.activeFormat = f` **之前** —— 这样 activeFormat
        //       是我们最后一个写的人,照片管线不可能把它改回去。
        let photo = AVCapturePhotoOutput()
        if s.canAddOutput(photo) {
            s.addOutput(photo)
            // 🔴 **.speed,不是 .balanced/.quality**。AVCapturePhotoOutput.h:348
            //    原文:"Setting the maxPhotoQualityPrioritization to .quality
            //    will turn on optical image stabilization if the
            //    -isHighPhotoQualitySupported of the source device's
            //    -activeFormat is true."
            //    而 OIS 一开,像素就与物理位姿脱钩(AVCaptureDevice.h:2311
            //    "The extrinsicMatrix and camera intrinsics should only be used
            //    when video stabilization is disabled"),内参这张照片就作废。
            //    .speed 还顺带关掉多帧融合 —— 融合出来的照片没有单一曝光时刻。
            photo.maxPhotoQualityPrioritization = .speed
            self.photoOutput = photo
            self.photoOutputNote = "installed"
        } else {
            self.photoOutputNote = "can_add_output_false"
        }
"""
assert s.count(c_old) == 1, "C anchor"
s = s.replace(c_old, c_new)

# ── D. start(): maxPhotoDimensions + 自证快照 ────────────────────────────
d_old = """        out.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String: Int(width),
            kCVPixelBufferHeightKey as String: Int(height),
        ]

        lock.lock(); session = s; lock.unlock()
"""
d_new = """        out.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String: Int(width),
            kCVPixelBufferHeightKey as String: Int(height),
        ]

        // ── 照片最高分辨率。
        //    AVCapturePhotoOutput.h:544 原文:"The dimensions set must match one
        //    of the dimensions returned by
        //    AVCaptureDeviceFormat.supportedMaxPhotoDimensions for the current
        //    active format. Changing this property may trigger a lengthy
        //    reconfiguration of the capture render pipeline so it is recommended
        //    that this is set before calling -[AVCaptureSession startRunning]."
        //    ⇒ 两条约束都在这里被满足:activeFormat 已经定下来了(上面那个
        //      do 块),而 startRunning 还没调(就在下面几行)。
        //    🔴 **取 activeFormat 支持的最大值,不换 activeFormat**。换格式就
        //      会降视频流 —— 而视频流 ≥1920×1440 是铁律。所以照片分辨率的上限
        //      由"视频流要的那个格式"决定,这是刻意的取舍,不是遗漏。
        if let photo = self.photoOutput {
            if #available(iOS 16.0, *) {
                var best = CMVideoDimensions(width: 0, height: 0)
                for v in device.activeFormat.supportedMaxPhotoDimensions {
                    let d = v
                    if Int64(d.width) * Int64(d.height)
                        > Int64(best.width) * Int64(best.height) {
                        best = d
                    }
                }
                if best.width > 0 && best.height > 0 {
                    photo.maxPhotoDimensions = best
                }
            } else {
                // iOS 15 档(本工程 IPHONEOS_DEPLOYMENT_TARGET = 15.0)。
                // maxPhotoDimensions 是 iOS 16 才有的;15 上只有这个已废弃的
                // 开关,AVCam 当年抄的也正是它。
                photo.isHighResolutionCaptureEnabled = true
            }
        }

        self.configuredVideoProof = Self.videoProofDict(
            device: device, videoOutput: out, photoOutput: self.photoOutput)

        lock.lock(); session = s; lock.unlock()
"""
assert s.count(d_old) == 1, "D anchor"
s = s.replace(d_old, d_new)

# ── E. captureOutput: 记下实际交付尺寸 ───────────────────────────────────
e_old = """        lock.lock()
        offered &+= 1
        if slot != nil { displaced &+= 1 }
        slot = pb
        lock.unlock()
"""
e_new = """        lock.lock()
        offered &+= 1
        if slot != nil { displaced &+= 1 }
        slot = pb
        // 拍照时把内参从视频流分辨率缩到照片分辨率,分母就是这两个数。
        latestFrameWidth = CVPixelBufferGetWidth(pb)
        latestFrameHeight = CVPixelBufferGetHeight(pb)
        lock.unlock()
"""
assert s.count(e_old) == 1, "E anchor"
s = s.replace(e_old, e_new)

io.open(p, "w", encoding="utf-8").write(s)
print("patched, delta bytes:", len(s) - len(orig))
