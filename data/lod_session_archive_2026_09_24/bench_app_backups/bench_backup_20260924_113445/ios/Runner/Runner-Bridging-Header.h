#import "GeneratedPluginRegistrant.h"

// [pw][vio] 跨端 C++ 传输层。iOS 与安卓编的是**同一个源文件**
// (安卓:android_ready/native/xrslam/CMakeLists.txt)。Swift 只看到裸传输;
// 配置与解释归 Dart。
#import "../../vendor/xrslam/transport/PwXrslamTransportCore.h"

// [pw][af] 跨端 CDAF 的 C ABI 门面(对焦三臂用)。真源在 pocketworld
// vendor/pw_af/,由 sync_from_production.sh 镜像并自证逐字节一致。
#import "../../vendor/pw_af/pw_af_c.h"

// [pw][bench-replay 2026-09-23] 台架回放的两个只读引擎读数(BODY_POSE 与求解遥测)。
// 真源在 pocketworld ios/Runner/PwBenchReplayEngineProbe.{h,c},由同步脚本镜像并自证
// 逐字节一致。生产桥接头不 import 它。
#import "PwBenchReplayEngineProbe.h"
