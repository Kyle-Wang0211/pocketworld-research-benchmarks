
// ════════════════════════════════════════════════════════════════════════
// MARK: - 高清拍照(零 ARKit 路径)
// ════════════════════════════════════════════════════════════════════════
//
// ══ 为什么这块必须存在 ═══════════════════════════════════════════════════
// 生产拍摄页现在由 ARKit 拥有相机:同一个 ARSession 既供预览又出高清照片
// (`OfficialAetherARKitPlugin.swift` 的 `captureHighResolutionFrame`)。
// 而 **iOS 一次只把后置相机给一个会话** —— 想让拍摄流程在完全不启动 ARKit
// 的情况下跑,照片就必须由我们自己这个 `AVCaptureSession` 拍。
//
// ══ 抄的是哪一份 ═════════════════════════════════════════════════════════
// Apple 官方样例 **AVCam: Building a Camera App**
//   文档页:https://developer.apple.com/documentation/avfoundation/avcam-building-a-camera-app
//   本轮实际对照的源码:AVCam/Swift/AVCam/PhotoCaptureDelegate.swift 与
//   AVCam/Swift/AVCam/CameraViewController.swift(样例包内文件名)。
// 逐条抄了:
//   · `CameraViewController.configureSession()` 里 "// Add photo output." 一段
//     —— `session.canAddOutput(photoOutput)` → `session.addOutput(photoOutput)`
//     → 置高清开关。见上面 start() 里同名注释处。
//   · `CameraViewController.capturePhoto(_:)` 的 settings 构造:
//       `var photoSettings = AVCapturePhotoSettings()`
//       `if self.photoOutput.availablePhotoCodecTypes.contains(.hevc) {`
//       `    photoSettings = AVCapturePhotoSettings(format: [AVVideoCodecKey: AVVideoCodecType.hevc]) }`
//     以及 "Use a separate object for the photo capture delegate to isolate
//     each capture life cycle." + 用
//     `inProgressPhotoCaptureDelegates[settings.uniqueID]` 持强引用
//     (样例注释原文:"The Photo Output keeps a weak reference to the photo
//      capture delegate so we store it in an array to maintain a strong
//      reference to this object until the capture is completed.")。
//   · `PhotoCaptureProcessor` 这个类本身:`init(with requestedPhotoSettings:…)`、
//     `didFinish()`、以及四个 delegate 回调
//       `photoOutput(_:willBeginCaptureFor:)`
//       `photoOutput(_:willCapturePhotoFor:)`
//       `photoOutput(_:didFinishProcessingPhoto:error:)`  ← `photoData = photo.fileDataRepresentation()`
//       `photoOutput(_:didFinishCaptureFor:error:)`       ← 错误检查 → `guard let photoData` → 落盘 → `didFinish()`
//
// ══ 三处**刻意的偏离**(不是抄漏,是这条管线要的不一样)═══════════════════
//  (a) 落盘位置:AVCam 在 `didFinishCaptureFor` 里走 `PHPhotoLibrary` +
//      `PHAssetCreationRequest` 存进**用户相册**。我们改成写 app 沙盒
//      `Documents/pw_photos/`。理由:重建管线读的是沙盒里的照片 + sidecar,
//      而且我们没有、也不该要相册写权限。
//  (b) `flashMode`:AVCam 是 `.auto`。我们**钉死 `.off`**。生产的 ARKit 路径
//      根本不会打闪光(ARKit 不给 API),一张打了闪的照片与同批未打闪的照片
//      在光度上不是一套数据;而且闪光会改变曝光时长,`exposure_s` 就不再能
//      与视频流的曝光中点对齐。
//  (c) Live Photo / 深度 / previewPhotoFormat:AVCam 全都接。我们全不接。
//      Live Photo 会多拍一段视频(抢带宽、抢 ISP);深度要虚拟多摄;缩略图
//      我们不用。少接一项就少一处能改变 resolvedSettings 的变量。
//
// ══ 🔴 内参:照片自己的标定数据**拿不到**,这是 Apple 的硬约束 ═══════════
// `AVCapturePhotoOutput.h:1496` 原文:"you may only set this property to YES
// if your AVCapturePhotoOutput's cameraCalibrationDataDeliverySupported
// property is YES **and 2 or more devices are selected for virtual device
// constituent photo delivery**."
// 我们是单摄(`.builtInWideAngleCamera`)⇒ 这条路在本配置下永远关着。
// 所以内参走**第二条**:拿同一会话视频连接上的
// `kCMSampleBufferAttachmentKey_CameraIntrinsicMatrix`(它只在
// AVCaptureVideoDataOutput 的 connection 上可用,见 AVCaptureSession.h:1282),
// 按分辨率比例缩到照片尺寸。
// **两条路都在代码里,sidecar 里写明这张照片走的是哪一条**(`intrinsics_provenance`)
// —— 不猜、不假装。
//
// ══ 🔴 分辨率铁律:照片不许降视频流 ═══════════════════════════════════════
// 视频流 ≥1920×1440 喂 VIO,是不能动的。所以:
//   · 照片输出在 `beginConfiguration` 块里加,而 `device.activeFormat = f`
//     在那之后才写 ⇒ **我们是最后一个写 activeFormat 的人**;
//   · `maxPhotoDimensions` 只在 `activeFormat.supportedMaxPhotoDimensions`
//     里挑最大的,**绝不为了照片去换 activeFormat**;
//   · 运行期自证:`configuredVideoProof`(startRunning 之前)与拍照完成时
//     再取一次的快照逐项比,连同两次之间视频流交付的帧数一起写进 sidecar 的
//     `video_stream_unchanged`。降档了就会在那里显形。

/// 一次拍照的结果。与 `pw_camera_slot_photo_result` 的 9 个 double 一一对应。
fileprivate struct PwPhotoResult {
    let requestId: Int64
    let path: String
    let fx: Double
    let fy: Double
    let cx: Double
    let cy: Double
    let width: Double
    let height: Double
    /// 拍照时刻,秒,**host clock,与视频流 PTS 同域**。
    /// `AVCapturePhotoOutput.h:1990` 原文:"The time at which this image was
    /// captured, synchronized to the synchronizationClock of the
    /// AVCaptureSession … analogous to CMSampleBufferGetPresentationTimeStamp()."
    let tSeconds: Double
    let exposureSeconds: Double
}

// MARK: 视频档快照(自证用)

extension PwCameraSlotImpl {
    /// 把"视频流现在是什么档"原样拍成一个可 JSON 化的字典。
    /// 只读,不改任何设置。
    fileprivate static func videoProofDict(
        device: AVCaptureDevice,
        videoOutput: AVCaptureVideoDataOutput,
        photoOutput: AVCapturePhotoOutput?
    ) -> [String: Any] {
        let f = device.activeFormat
        let d = CMVideoFormatDescriptionGetDimensions(f.formatDescription)
        let sub = CMFormatDescriptionGetMediaSubType(f.formatDescription)
        var dict: [String: Any] = [
            "active_format_w": Int(d.width),
            "active_format_h": Int(d.height),
            "active_format_subtype": Int(sub),
            "active_format_binned": f.isVideoBinned,
            "min_frame_duration_s": CMTimeGetSeconds(device.activeVideoMinFrameDuration),
            "max_frame_duration_s": CMTimeGetSeconds(device.activeVideoMaxFrameDuration),
        ]
        if let vs = videoOutput.videoSettings,
           let w = vs[kCVPixelBufferWidthKey as String] as? Int,
           let h = vs[kCVPixelBufferHeightKey as String] as? Int {
            dict["video_settings_w"] = w
            dict["video_settings_h"] = h
        }
        if let conn = videoOutput.connection(with: .video) {
            dict["intrinsic_delivery_enabled"] = conn.isCameraIntrinsicMatrixDeliveryEnabled
            dict["active_stabilization_mode"] = conn.activeVideoStabilizationMode.rawValue
        }
        if let p = photoOutput, #available(iOS 16.0, *) {
            dict["photo_max_w"] = Int(p.maxPhotoDimensions.width)
            dict["photo_max_h"] = Int(p.maxPhotoDimensions.height)
        }
        return dict
    }

    /// 取当前视频档快照。会话没起来时返回空字典。
    fileprivate func currentVideoProof() -> [String: Any] {
        lock.lock()
        let s = sessionForProof
        lock.unlock()
        guard let dev = device, let sess = s else { return [:] }
        guard let vout = sess.outputs.compactMap({ $0 as? AVCaptureVideoDataOutput }).first
        else { return [:] }
        return Self.videoProofDict(
            device: dev, videoOutput: vout, photoOutput: photoOutput)
    }
}

// MARK: 拍照受理 / 结果轮询

extension PwCameraSlotImpl {
    /// 触发一次高清拍照。同步只做校验与受理,拍照本身是异步的。
    fileprivate func capturePhoto(requestId: Int64) -> Int32 {
        lock.lock()
        let running = session != nil
        lock.unlock()
        guard running else { return -1 }
        guard let out = photoOutput else { return -2 }

        photoLock.lock()
        if inFlightPhotos[requestId] != nil {
            photoLock.unlock()
            return -3
        }
        photoLock.unlock()

        guard let dir = Self.photosDirectory() else { return -4 }

        // ── settings 构造:抄 AVCam `capturePhoto(_:)`。
        var photoSettings = AVCapturePhotoSettings()
        if out.availablePhotoCodecTypes.contains(.hevc) {
            photoSettings = AVCapturePhotoSettings(
                format: [AVVideoCodecKey: AVVideoCodecType.hevc])
        }
        // 偏离 (b):AVCam 是 `.auto`。见文件上方说明。
        photoSettings.flashMode = .off
        // 与 output 的 maxPhotoQualityPrioritization 同档 —— 不开 OIS、不做多帧融合。
        photoSettings.photoQualityPrioritization = .speed
        if #available(iOS 16.0, *) {
            // 逐张也要写一遍:AVCapturePhotoOutput.h:1454 —— settings 的
            // maxPhotoDimensions "defaults to the smallest dimensions returned
            // by AVCaptureDeviceFormat.supportedMaxPhotoDimensions"。
            // **默认是最小的那个**,不写这一行就等于主动要了最低分辨率。
            photoSettings.maxPhotoDimensions = out.maxPhotoDimensions
        } else {
            photoSettings.isHighResolutionPhotoEnabled = true
        }

        let ext = photoSettings.processedFileType == .jpg ? "jpg" : "heic"
        let url = dir.appendingPathComponent("\(requestId).\(ext)")

        let beforeProof = configuredVideoProof
        lock.lock(); let offeredBefore = offered; lock.unlock()

        // 抄 AVCam:"Use a separate object for the photo capture delegate to
        // isolate each capture life cycle."
        let processor = PwPhotoCaptureProcessor(
            with: photoSettings,
            requestId: requestId,
            outputURL: url,
            beforeProof: beforeProof,
            offeredBefore: offeredBefore
        ) { [weak self] proc, result in
            guard let self else { return }
            // 抄 AVCam 的 completionHandler:结果收走之后立刻把 delegate 放掉。
            self.photoLock.lock()
            self.inFlightPhotos[proc.requestId] = nil
            if let r = result {
                self.completedPhotos.append(r)
                while self.completedPhotos.count > Self.kCompletedPhotoCap {
                    self.completedPhotos.removeFirst()
                    self.photoDropped &+= 1
                }
            }
            let dropped = self.photoDropped
            self.photoLock.unlock()
            if result == nil {
                NSLog("[PwCameraSlot] photo \(proc.requestId) failed")
            } else if dropped > 0 {
                NSLog("[PwCameraSlot] photo results dropped: \(dropped) "
                    + "(消费方轮询太慢,FIFO 上限 \(Self.kCompletedPhotoCap))")
            }
        }

        // 🔴 **先持强引用再发起**。AVCam 原文:"The Photo Output keeps a weak
        //    reference to the photo capture delegate so we store it in an array
        //    to maintain a strong reference to this object until the capture is
        //    completed." 顺序反了 = delegate 可能在回调前就被释放。
        photoLock.lock()
        inFlightPhotos[requestId] = processor
        photoLock.unlock()

        photoQueue.async { [weak self] in
            guard let self else { return }
            processor.attach(slot: self)
            out.capturePhoto(with: photoSettings, delegate: processor)
        }
        return 0
    }

    /// 取走**最早一个**已完成的结果。0 = 有结果(已消费),-1 = 还没有,
    /// -2 = 路径放不下(结果**不消费**,加大 cap 再来)。
    fileprivate func photoResult(
        into outPath: UnsafeMutablePointer<CChar>, cap: Int32,
        nums: UnsafeMutablePointer<Double>
    ) -> Int32 {
        guard cap > 0 else { return -2 }
        photoLock.lock()
        guard let r = completedPhotos.first else {
            photoLock.unlock()
            return -1
        }
        let bytes = Array(r.path.utf8)
        guard bytes.count + 1 <= Int(cap) else {
            photoLock.unlock()
            return -2
        }
        completedPhotos.removeFirst()
        photoLock.unlock()

        for (i, b) in bytes.enumerated() { outPath[i] = CChar(bitPattern: b) }
        outPath[bytes.count] = 0
        nums[0] = Double(r.requestId)
        nums[1] = r.fx
        nums[2] = r.fy
        nums[3] = r.cx
        nums[4] = r.cy
        nums[5] = r.width
        nums[6] = r.height
        nums[7] = r.tSeconds
        nums[8] = r.exposureSeconds
        return 0
    }

    /// 拍照时刻的视频流内参 + 它所参照的分辨率。`nil` = 还没收到过内参。
    fileprivate func videoIntrinsicsSnapshot()
        -> (fx: Double, fy: Double, cx: Double, cy: Double, w: Int, h: Int)? {
        lock.lock(); defer { lock.unlock() }
        guard fx > 0, latestFrameWidth > 0, latestFrameHeight > 0 else { return nil }
        return (fx, fy, cx, cy, latestFrameWidth, latestFrameHeight)
    }

    fileprivate var offeredCount: Int64 {
        lock.lock(); defer { lock.unlock() }
        return offered
    }

    /// `Documents/pw_photos/`,不存在就建。建不出来返回 nil。
    fileprivate static func photosDirectory() -> URL? {
        guard let docs = FileManager.default.urls(
            for: .documentDirectory, in: .userDomainMask).first else { return nil }
        let dir = docs.appendingPathComponent("pw_photos", isDirectory: true)
        if !FileManager.default.fileExists(atPath: dir.path) {
            do {
                try FileManager.default.createDirectory(
                    at: dir, withIntermediateDirectories: true)
            } catch {
                NSLog("[PwCameraSlot] pw_photos 建不出来: \(error)")
                return nil
            }
        }
        return dir
    }
}

// MARK: - PwPhotoCaptureProcessor
//
// 抄 AVCam 的 `PhotoCaptureProcessor`(AVCam/Swift/AVCam/PhotoCaptureDelegate.swift)。
// 一次拍照一个实例;`completionHandler` 让持有者在拍完后把它放掉。

fileprivate final class PwPhotoCaptureProcessor: NSObject {
    private(set) var requestedPhotoSettings: AVCapturePhotoSettings
    let requestId: Int64

    private let outputURL: URL
    private let beforeProof: [String: Any]
    private let offeredBefore: Int64
    private let completionHandler: (PwPhotoCaptureProcessor, PwPhotoResult?) -> Void

    private weak var slot: PwCameraSlotImpl?

    // 回调之间攒下来的东西。全部只在 delegate 回调里写,在 didFinish 里读。
    private var photoData: Data?
    private var photoTimestamp: Double = 0
    private var resolvedWidth: Int = 0
    private var resolvedHeight: Int = 0
    private var exifExposureSeconds: Double = -1
    private var photoCalibration:
        (fx: Double, fy: Double, cx: Double, cy: Double, refW: Double, refH: Double)?
    private var deviceExposureSeconds: Double = -1
    private var failureNote: String?

    init(with requestedPhotoSettings: AVCapturePhotoSettings,
         requestId: Int64,
         outputURL: URL,
         beforeProof: [String: Any],
         offeredBefore: Int64,
         completionHandler: @escaping (PwPhotoCaptureProcessor, PwPhotoResult?) -> Void) {
        self.requestedPhotoSettings = requestedPhotoSettings
        self.requestId = requestId
        self.outputURL = outputURL
        self.beforeProof = beforeProof
        self.offeredBefore = offeredBefore
        self.completionHandler = completionHandler
    }

    func attach(slot: PwCameraSlotImpl) { self.slot = slot }

    /// 抄 AVCam 的 `didFinish()`:收尾 + 调 completionHandler。
    /// 我们的收尾是"落盘 + 写 sidecar",AVCam 的是"存进相册"(偏离 (a))。
    private func didFinish() {
        guard let data = photoData else {
            completionHandler(self, nil)
            return
        }

        // 真实像素尺寸从**文件头**读,不是从 resolvedSettings 抄。
        // CGImageSource 只读头不解码,代价可忽略;两者不一致时两个数都写进
        // sidecar,由人去看,而不是我们挑一个。
        var fileW = 0
        var fileH = 0
        if let src = CGImageSourceCreateWithData(data as CFData, nil),
           let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil)
            as? [CFString: Any] {
            fileW = (props[kCGImagePropertyPixelWidth] as? Int) ?? 0
            fileH = (props[kCGImagePropertyPixelHeight] as? Int) ?? 0
        }
        let imageW = fileW > 0 ? fileW : resolvedWidth
        let imageH = fileH > 0 ? fileH : resolvedHeight
        let dimsProvenance = fileW > 0 ? "image_file_header" : "resolved_photo_settings"

        // ── 内参 ──────────────────────────────────────────────────────────
        var fx = 0.0, fy = 0.0, cx = 0.0, cy = 0.0
        var intrinsicsProvenance = "none"
        var scaleInfo: [String: Any] = [:]
        if let c = photoCalibration, c.refW > 0, c.refH > 0, imageW > 0, imageH > 0 {
            // 第一条路:照片自己的 AVCameraCalibrationData。本配置(单摄)下
            // 按 Apple 头文件它永远拿不到 —— 留着是因为多摄/虚拟设备一旦接上
            // 它就活了,而且真活了的时候必须优先用它。
            let sx = Double(imageW) / c.refW
            let sy = Double(imageH) / c.refH
            fx = c.fx * sx; fy = c.fy * sy
            cx = c.cx * sx; cy = c.cy * sy
            intrinsicsProvenance = "photo_camera_calibration_data"
            scaleInfo = ["ref_w": c.refW, "ref_h": c.refH, "sx": sx, "sy": sy]
        } else if let v = slot?.videoIntrinsicsSnapshot(), imageW > 0, imageH > 0 {
            // 第二条路:同一会话视频连接的逐帧内参,按分辨率比例缩。
            let sx = Double(imageW) / Double(v.w)
            let sy = Double(imageH) / Double(v.h)
            fx = v.fx * sx; fy = v.fy * sy
            cx = v.cx * sx; cy = v.cy * sy
            intrinsicsProvenance = "video_connection_scaled"
            scaleInfo = [
                "video_w": v.w, "video_h": v.h, "sx": sx, "sy": sy,
                // 非等比就是宽高比不一致,缩放这件事本身就不对 —— 写出来。
                "aspect_mismatch": abs(sx - sy) > 1e-3,
            ]
        }

        // ── 曝光 ──────────────────────────────────────────────────────────
        var exposure = 0.0
        var exposureProvenance = "none"
        if exifExposureSeconds >= 0 {
            exposure = exifExposureSeconds
            exposureProvenance = "photo_exif_exposure_time"
        } else if deviceExposureSeconds >= 0 {
            exposure = deviceExposureSeconds
            exposureProvenance = "device_exposure_duration_at_completion"
        }

        // ── 落盘 ──────────────────────────────────────────────────────────
        do {
            try data.write(to: outputURL, options: .atomic)
        } catch {
            NSLog("[PwCameraSlot] 照片写不下去 \(outputURL.path): \(error)")
            completionHandler(self, nil)
            return
        }

        // ── sidecar。键与生产 ARKit 路径同名(`t` / `intrinsics_fxfycxcy`,
        //    见 OfficialAetherARKitPlugin.swift 的 per-photo .json schema),
        //    额外键只加不改。
        let afterProof = slot?.currentVideoProof() ?? [:]
        let offeredAfter = slot?.offeredCount ?? 0
        var sidecar: [String: Any] = [
            "version": 1,
            "source": "avfoundation_photo_output",
            "native_role": "pw_camera_slot_photo_output",
            "request_id": requestId,
            "t": photoTimestamp,
            "image_w": imageW,
            "image_h": imageH,
            "image_dims_provenance": dimsProvenance,
            "resolved_photo_w": resolvedWidth,
            "resolved_photo_h": resolvedHeight,
            "intrinsics_fxfycxcy": [fx, fy, cx, cy],
            "intrinsics_provenance": intrinsicsProvenance,
            "intrinsics_scale": scaleInfo,
            "exposure_s": exposure,
            "exposure_provenance": exposureProvenance,
            "photo_file_type": requestedPhotoSettings.processedFileType?.rawValue ?? "unknown",
            "photo_settings_unique_id": requestedPhotoSettings.uniqueID,
            "flash_mode": requestedPhotoSettings.flashMode.rawValue,
            "video_stream_unchanged": [
                "configured": beforeProof,
                "at_photo": afterProof,
                "unchanged": PwPhotoCaptureProcessor.proofsEqual(beforeProof, afterProof),
                "video_frames_offered_before": offeredBefore,
                "video_frames_offered_after": offeredAfter,
            ],
        ]
        if let note = failureNote { sidecar["capture_note"] = note }

        let sidecarURL = outputURL.deletingPathExtension()
            .appendingPathExtension("json")
        do {
            let json = try PWJSONSafety.data(withJSONObject: sidecar)
            try json.write(to: sidecarURL, options: .atomic)
        } catch {
            // sidecar 写不出去 = 这张照片没有内参,对下游等于废片。
            // 照片一并删掉,免得留下一张"看起来有、其实用不了"的文件。
            NSLog("[PwCameraSlot] sidecar 写不下去 \(sidecarURL.path): \(error)")
            try? FileManager.default.removeItem(at: outputURL)
            completionHandler(self, nil)
            return
        }

        completionHandler(self, PwPhotoResult(
            requestId: requestId,
            path: outputURL.path,
            fx: fx, fy: fy, cx: cx, cy: cy,
            width: Double(imageW), height: Double(imageH),
            tSeconds: photoTimestamp,
            exposureSeconds: exposure))
    }

    /// 只比"会改变视频流质量"的那几项,不比 photo_max_*(那本来就是照片侧的)。
    fileprivate static func proofsEqual(_ a: [String: Any], _ b: [String: Any]) -> Bool {
        let keys = ["active_format_w", "active_format_h", "active_format_subtype",
                    "active_format_binned", "min_frame_duration_s",
                    "max_frame_duration_s", "video_settings_w", "video_settings_h",
                    "intrinsic_delivery_enabled", "active_stabilization_mode"]
        if a.isEmpty || b.isEmpty { return false }
        for k in keys {
            let x = a[k], y = b[k]
            if x == nil && y == nil { continue }
            guard let xv = x as? NSObject, let yv = y as? NSObject, xv == yv else {
                return false
            }
        }
        return true
    }
}

extension PwPhotoCaptureProcessor: AVCapturePhotoCaptureDelegate {
    /*
     抄 AVCam:"This extension includes all the delegate callbacks for
     AVCapturePhotoCaptureDelegate protocol"。我们只实现用得到的四个;
     Live Photo 那两个不实现,因为我们根本没开 Live Photo。
    */

    func photoOutput(_ output: AVCapturePhotoOutput,
                     willBeginCaptureFor resolvedSettings: AVCaptureResolvedPhotoSettings) {
        // AVCam 在这里判 Live Photo;我们在这里把**系统解析后的**照片尺寸
        // 记下来(AVCapturePhotoOutput.h:1806:"The resolved dimensions of the
        // photo buffer that will be delivered")。它是"我们要到了多大"的凭据,
        // 与最终文件头里的尺寸互为对照。
        resolvedWidth = Int(resolvedSettings.photoDimensions.width)
        resolvedHeight = Int(resolvedSettings.photoDimensions.height)
    }

    func photoOutput(_ output: AVCapturePhotoOutput,
                     willCapturePhotoFor resolvedSettings: AVCaptureResolvedPhotoSettings) {
        // AVCam 在这里放快门动画。我们没有 UI —— 这里只抓一次设备当前曝光,
        // 作为 EXIF 拿不到时的兜底(读法与 captureOutput 里那处同源)。
        if let d = slot?.device {
            let e = CMTimeGetSeconds(d.exposureDuration)
            deviceExposureSeconds = (e.isFinite && e >= 0) ? e : -1
        }
    }

    func photoOutput(_ output: AVCapturePhotoOutput,
                     didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        if let error = error {
            // AVCam 原文只 print。我们把它记下来写进 sidecar。
            failureNote = "didFinishProcessingPhoto: \(error.localizedDescription)"
            NSLog("[PwCameraSlot] Error capturing photo: \(error)")
            return
        }
        photoData = photo.fileDataRepresentation()   // ← AVCam 逐字同句

        let t = CMTimeGetSeconds(photo.timestamp)
        photoTimestamp = t.isFinite ? t : 0

        // EXIF 曝光时间 = 这张照片自己的曝光,不是"回调那一刻设备的曝光"。
        if let exif = photo.metadata[kCGImagePropertyExifDictionary as String]
            as? [String: Any],
           let e = exif[kCGImagePropertyExifExposureTime as String] as? Double,
           e.isFinite, e >= 0 {
            exifExposureSeconds = e
        }

        // 单摄下按 Apple 头文件这里永远是 nil;留着是为了多摄接上时它自动生效。
        if let cal = photo.cameraCalibrationData {
            let m = cal.intrinsicMatrix
            let ref = cal.intrinsicMatrixReferenceDimensions
            photoCalibration = (
                fx: Double(m.columns.0.x), fy: Double(m.columns.1.y),
                cx: Double(m.columns.2.x), cy: Double(m.columns.2.y),
                refW: Double(ref.width), refH: Double(ref.height))
        }
    }

    func photoOutput(_ output: AVCapturePhotoOutput,
                     didFinishCaptureFor resolvedSettings: AVCaptureResolvedPhotoSettings,
                     error: Error?) {
        // 结构逐条抄 AVCam:错误 → didFinish();没数据 → didFinish();否则落盘。
        if let error = error {
            NSLog("[PwCameraSlot] Error capturing photo: \(error)")
            failureNote = (failureNote.map { $0 + " | " } ?? "")
                + "didFinishCaptureFor: \(error.localizedDescription)"
            didFinish()
            return
        }
        guard photoData != nil else {
            NSLog("[PwCameraSlot] No photo data resource")
            didFinish()
            return
        }
        didFinish()
    }
}

// ── C ABI 出口 ───────────────────────────────────────────────────────────

/// 触发一次高清拍照。**只受理,不等待** —— 结果异步进槽,用
/// `pw_camera_slot_photo_result` 轮询。
///
/// 返回 0 已受理;负数是失败码:
///   -1 相机没起来(先调 `pw_camera_slot_start`)
///   -2 这台设备/这个会话上装不了 AVCapturePhotoOutput(原因见 NSLog)
///   -3 同一个 requestId 还在飞
///   -4 沙盒 `Documents/pw_photos/` 建不出来
@_cdecl("pw_camera_slot_capture_photo")
public func pw_camera_slot_capture_photo(_ requestId: Int64) -> Int32 {
    return PwCameraSlotImpl.shared.capturePhoto(requestId: requestId)
}

/// 取走一个已完成的拍照结果。
///
/// - `outPath`:UTF-8 文件路径,写到 `cap` 字节为止(含结尾 NUL)。
/// - `outNums`:9 个 double,顺序固定
///   `[requestId, fx, fy, cx, cy, width, height, t, exposure]`。
///   `t` 是 host clock 秒,**与视频流 PTS 同域**;`exposure` 是秒。
///
/// 返回 0 = 有结果(已从队列里消费掉);-1 = 还没有;
/// -2 = `cap` 放不下这条路径(**结果不消费**,加大 cap 再来)。
///
/// 🔴 语义是 **FIFO 逐个取走**,不是"读最近一次"。连拍时先完成的先出,
/// 不会因为来不及轮询就被后一张顶掉(上限 32 张,超了丢最老的并 NSLog 计账)。
@_cdecl("pw_camera_slot_photo_result")
public func pw_camera_slot_photo_result(_ outPath: UnsafeMutablePointer<CChar>,
                                        _ cap: Int32,
                                        _ outNums: UnsafeMutablePointer<Double>) -> Int32 {
    return PwCameraSlotImpl.shared.photoResult(into: outPath, cap: cap, nums: outNums)
}
