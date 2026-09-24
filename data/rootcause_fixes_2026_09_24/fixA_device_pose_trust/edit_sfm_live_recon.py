#!/usr/bin/python3
# fixA: thread devicePoseTrusted through lib/official_capture/sfm_live_recon.dart
import sys
p = sys.argv[1]
s = open(p).read()


def rep(old, new, count=1):
    global s
    n = s.count(old)
    assert n == count, (n, old[:120])
    s = s.replace(old, new)


# 1. SfmFedFrameMeta fields
rep("""    this.arkitQuatWxyz,
    this.arkitTransTxyz,
    this.arkitCameraCenterWorld,
  });
  final String jpegPath;""", """    this.arkitQuatWxyz,
    this.arkitTransTxyz,
    this.arkitCameraCenterWorld,
    this.devicePoseTrusted = true,
    this.deviceTrackingState,
    this.devicePoseTrustReason,
  });
  final String jpegPath;""")
rep("""  /// ARKit camera center in the gravity-aligned world frame, meters.
  final List<double>? arkitCameraCenterWorld;
}""", """  /// ARKit camera center in the gravity-aligned world frame, meters.
  final List<double>? arkitCameraCenterWorld;

  /// [DEVICE-POSE-TRUST 2026-09-24] 共享契约位(agent A/B/C):false ⇒ 核不得
  /// 把该帧摆在设备位姿上、不得拿它做 Sim3 对齐对/位姿先验;Dart 侧也不拿它
  /// 的 ARKit 旋转做重力对齐。拍摄期喂帧路径一律显式赋值
  /// (OfficialHighResReconstructionInput.devicePoseTrust);缺省 true 只为
  /// 兼容本字段出现之前落盘的 fed 记录(当时一律按可信喂)—— 续跑读旧记录
  /// 时是否改判由 resume 侧决定。
  final bool devicePoseTrusted;

  /// 追踪器对该帧报告的原始状态(跨端词表),审计用;null = 未报告。
  final String? deviceTrackingState;

  /// DevicePoseTrust.reason,审计用。
  final String? devicePoseTrustReason;
}

/// [DEVICE-POSE-TRUST 2026-09-24] 一行 `official_sfm_fed_frames.jsonl` 记录。
/// 纯函数(便于单测);[SfmLiveRecon._persistFedMeta] 原样落盘。
/// `devicePoseTrusted` 恒写出;[coreHonorsDevicePoseTrust] = 这一帧是不是经
/// 带信任位的核 ABI 喂进去的(false = 旧核回退路径:核仍按旧行为把它摆在
/// 设备位姿上,分析时不能把 devicePoseTrusted=false 当成"核没用它")。
Map<String, Object?> sfmFedFrameRecord(
  int frameId,
  SfmFedFrameMeta m, {
  bool? coreHonorsDevicePoseTrust,
}) {
  final meta = <String, Object?>{
    'frameId': frameId,
    'jpegPath': m.jpegPath,
    'grayW': m.grayW,
    'grayH': m.grayH,
    if (m.captureTimestamp != null) 'captureTimestamp': m.captureTimestamp,
    'devicePoseTrusted': m.devicePoseTrusted,
    'deviceTrackingState': m.deviceTrackingState,
    if (m.devicePoseTrustReason != null)
      'devicePoseTrustReason': m.devicePoseTrustReason,
    if (coreHonorsDevicePoseTrust != null)
      'coreHonorsDevicePoseTrust': coreHonorsDevicePoseTrust,
  };
  if (m.arkitQuatWxyz != null &&
      m.arkitTransTxyz != null &&
      m.arkitCameraCenterWorld != null) {
    meta.addAll(<String, Object?>{
      // [07-28 勘误] 旧标签让外部分析误以为已做 COLMAP 相机系翻转;
      // 实际存的是 ARKit 相机轴约定的 CamFromWorld(C=diag(1,-1,-1)
      // **未**应用——gravity align 公式 R_w=R_ark^T·C·R_col 自带 C,
      // 吃的就是 raw)。标签改为显式声明,数据一字未动。
      'arkitPoseConvention':
          'worldAlignment.gravity; CamFromWorld inverted from ARKit '
          'cameraToWorld, in ARKit CAMERA AXES (COLMAP C=diag(1,-1,-1) '
          'flip NOT applied); plus camera center in world',
      'arkitCamFromWorldQwxyz': m.arkitQuatWxyz,
      'arkitCamFromWorldTxyz': m.arkitTransTxyz,
      'arkitCameraCenterWorld': m.arkitCameraCenterWorld,
    });
  }
  return meta;
}""")

# 2. _SpooledFrame
rep("""    required this.quatWxyz,
    required this.trans,
  });
  final int seq;""", """    required this.quatWxyz,
    required this.trans,
    required this.devicePoseTrusted,
  });
  final int seq;""")
rep("""  final Float64List? quatWxyz;
  final Float64List? trans;
}

/// Identifies the coordinate-space contract""", """  final Float64List? quatWxyz;
  final Float64List? trans;
  final bool devicePoseTrusted;
}

/// Identifies the coordinate-space contract""")

# 3. offerFrame meta + send/spool
rep("""      arkitQuatWxyz: quatWxyz?.toList(), // ARKit CamFromWorld (gravity frame)
      arkitTransTxyz: trans?.toList(),
      arkitCameraCenterWorld: cameraCenterWorld,
    );
""", """      arkitQuatWxyz: quatWxyz?.toList(), // ARKit CamFromWorld (gravity frame)
      arkitTransTxyz: trans?.toList(),
      arkitCameraCenterWorld: cameraCenterWorld,
      // [DEVICE-POSE-TRUST] 追踪器对这张照片自己那一帧的判决。位姿照样随帧
      // 记下(审计/续跑),但核与 Dart 重力对齐都不得把它当设备位姿用。
      devicePoseTrusted: feed.devicePoseTrusted,
      deviceTrackingState: feed.devicePoseTrust.trackerState,
      devicePoseTrustReason: feed.devicePoseTrust.reason,
    );
    if (!feed.devicePoseTrusted) {
      DeviceLog.log(
        'SfmLive',
        'frame#$seq device pose UNTRUSTED (${feed.devicePoseTrust.reason}) '
            '— fed for image-evidence registration only',
      );
    }
""")
rep("""        cy,
        quatWxyz,
        trans,
      );
    } else {
      _spool.add(
        _SpooledFrame(
          seq: seq,
          path: feed.jpegPath,
          w: feed.imageWidth,
          h: feed.imageHeight,
          captureTimestamp: feed.captureTimestamp,
          fx: fx,
          fy: fy,
          cx: cx,
          cy: cy,
          quatWxyz: quatWxyz,
          trans: trans,
        ),
      );""", """        cy,
        quatWxyz,
        trans,
        feed.devicePoseTrusted,
      );
    } else {
      _spool.add(
        _SpooledFrame(
          seq: seq,
          path: feed.jpegPath,
          w: feed.imageWidth,
          h: feed.imageHeight,
          captureTimestamp: feed.captureTimestamp,
          fx: fx,
          fy: fy,
          cx: cx,
          cy: cy,
          quatWxyz: quatWxyz,
          trans: trans,
          devicePoseTrusted: feed.devicePoseTrusted,
        ),
      );""")
# 4. _sendJpegFrameCmd
rep("""    Float64List? q,
    Float64List? t,
  ) {
    _inFlight++;""", """    Float64List? q,
    Float64List? t,
    bool devicePoseTrusted,
  ) {
    _inFlight++;""")
rep("""      'q': q,
      't': t,
    });
  }""", """      'q': q,
      't': t,
      'devicePoseTrusted': devicePoseTrusted,
    });
  }""")
rep("""            entry.quatWxyz,
            entry.trans,
          );
        } catch (e) {""", """            entry.quatWxyz,
            entry.trans,
            entry.devicePoseTrusted,
          );
        } catch (e) {""")
rep("""          trans: m.arkitTransTxyz != null
              ? Float64List.fromList(m.arkitTransTxyz!)
              : null,
        ),
      );
    }""", """          trans: m.arkitTransTxyz != null
              ? Float64List.fromList(m.arkitTransTxyz!)
              : null,
          devicePoseTrusted: m.devicePoseTrusted,
        ),
      );
    }""")
# 5. frame_done persist
rep("""        } else if (ok && meta != null && frameId >= 0) {
          _fedMeta[frameId] = meta;
          _persistFedMeta(frameId, meta);
        }""", """        } else if (ok && meta != null && frameId >= 0) {
          _fedMeta[frameId] = meta;
          _persistFedMeta(
            frameId,
            meta,
            coreHonorsDevicePoseTrust: msg['trustAbi'] as bool?,
          );
        }""")
a = s.index("  void _persistFedMeta(int frameId, SfmFedFrameMeta m) {")
b = s.index("      final line = '${jsonEncode(meta)}\\n';", a)
s = s[:a] + """  void _persistFedMeta(
    int frameId,
    SfmFedFrameMeta m, {
    bool? coreHonorsDevicePoseTrust,
  }) {
    try {
      final dir = File(_dbPath).parent.path;
      final meta = sfmFedFrameRecord(
        frameId,
        m,
        coreHonorsDevicePoseTrust: coreHonorsDevicePoseTrust,
      );
""" + s[b:]
# 6. gravity lookup
rep("""      arkitQuatWxyzOf: (frameId) => _fedMeta[frameId]?.arkitQuatWxyz,
      diag: diag,""", """      // [DEVICE-POSE-TRUST] 追踪器不承认的帧不贡献设备旋转。
      arkitQuatWxyzOf: (frameId) {
        final m = _fedMeta[frameId];
        return m != null && m.devicePoseTrusted ? m.arkitQuatWxyz : null;
      },
      diag: diag,""")
# 7. worker addJpegFrame + frame_done + frameCenters
rep("""            quatWxyz: (msg['q'] as Float64List?)?.toList(),
            translation: (msg['t'] as Float64List?)?.toList(),
          );
          sw.stop();""", """            quatWxyz: (msg['q'] as Float64List?)?.toList(),
            translation: (msg['t'] as Float64List?)?.toList(),
            // [DEVICE-POSE-TRUST] 缺字段按不可信(fail-closed)。
            devicePoseTrusted: msg['devicePoseTrusted'] == true,
          );
          sw.stop();""")
rep("""            if (throttledCum >= 0) 'throttledCum': throttledCum,
          });""", """            if (throttledCum >= 0) 'throttledCum': throttledCum,
            'trustAbi': r.devicePoseTrustHonored,
          });""")
rep("""              final q = msg['q'] as Float64List?;
              final t = msg['t'] as Float64List?;
              if (q != null && t != null) {""", """              final q = msg['q'] as Float64List?;
              final t = msg['t'] as Float64List?;
              // [DEVICE-POSE-TRUST] 不可信帧不提供设备相机中心。
              if (q != null && t != null && msg['devicePoseTrusted'] == true) {""")
open(p, 'w').write(s)
print('ok')
