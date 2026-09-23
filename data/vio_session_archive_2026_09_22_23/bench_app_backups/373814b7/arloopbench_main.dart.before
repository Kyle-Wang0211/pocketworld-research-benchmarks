// arloopbench —— AR 最小回路台架。
//
// 🔴 这是**台架**,不是生产。生产的 PocketWorld 一个字节都不碰。
// 等到 XRSLAM 在精度/稳定性上跟 ARKit 持平或更好,再谈上生产。
//
// 它只做一件事:把相机帧经由我们自己算的 UV 与投影送进 Filament,看背景
// 出不出得来。`lib/vio/**` 是 pocketworld 的**镜像**(真源在那边),用
// ./sync_from_production.sh 同步并自证逐字节一致。

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show DeviceOrientation, SystemChrome;

import 'vio/calib/imu_calib_capture_page.dart';
import 'vio/render/ar_minimal_loop_page.dart';
import 'vio/render/pose_chain_probe_page.dart';
import 'vio/render/zupt_probe_page.dart';
import 'vio/render/zero_arkit_preview_probe_page.dart';
import 'vio/render/zero_arkit_capture_probe_page.dart';

// 🔴 [2026-09-22 用户原话「拍摄页面竟然可以反转成横向?锁死竖向屏幕」]
// 台架所有探针页都按竖屏算 3:4 框与 displayRotation=0,横过来预览与内参
// 口径就对不上。锁法照 Flutter 官方 SystemChrome.setPreferredOrientations
// 文档示例(api.flutter.dev/flutter/services/SystemChrome/setPreferredOrientations.html),
// 并把 Info.plist 的 UISupportedInterfaceOrientations 只留 Portrait——
// iOS 上两处都要,只改 Dart 侧系统仍可能在启动瞬间横过来。
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations(
      <DeviceOrientation>[DeviceOrientation.portraitUp]);
  runApp(const ArLoopBenchApp());
}

class ArLoopBenchApp extends StatelessWidget {
  const ArLoopBenchApp({super.key});

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      title: 'AR Loop Bench',
      debugShowCheckedModeBanner: false,
      // 两个验证页,用 --dart-define 选:
      //   默认              = AR 最小回路(会开摄像头)
      //   PW_POSE_CHAIN=true = 位姿链探针(**不开摄像头**,纯几何)
      //   PW_ZUPT=still | moving = 零速检测探针(**不开摄像头**,纯 IMU)
      //   一次只采一种状态,分两次跑。空串 = 不选这一页。
      //   PW_IMU_CALIB=true = 六位置法 IMU 内参标定采集(**不开摄像头**,纯 IMU)
      //   PW_ZERO_ARKIT_PREVIEW=true = 零 ARKit 臂预览探针(**会开摄像头**,3:4 框)
      //   PW_ZERO_ARKIT_CAPTURE=true = 零 ARKit 臂端到端拍摄探针(**会开摄像头**
      //     + 建 XRSLAM 会话 + 快门写 JPEG/sidecar 到 Documents/;优先级最前)
      home: bool.fromEnvironment('PW_ZERO_ARKIT_CAPTURE')
          ? ZeroArkitCaptureProbePage()
          : bool.fromEnvironment('PW_ZERO_ARKIT_PREVIEW')
          ? ZeroArkitPreviewProbePage()
          : bool.fromEnvironment('PW_IMU_CALIB')
          ? ImuCalibCapturePage()
          : String.fromEnvironment('PW_ZUPT') != ''
              ? ZuptProbePage()
              : bool.fromEnvironment('PW_POSE_CHAIN')
                  ? PoseChainProbePage()
                  : ArMinimalLoopPage(),
    );
  }
}
