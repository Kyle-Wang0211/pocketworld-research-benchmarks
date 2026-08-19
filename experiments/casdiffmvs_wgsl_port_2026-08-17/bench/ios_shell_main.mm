// CasDiffMVS A4 bench 的 iOS 壳(方案 A:dylib 打包)。
//
// 职责只有四件:① stdout/stderr 重定向到 Documents/bench_result.txt(拔线也能拿结果);
// ② 从 bundle 里取 model/inputs 组 argv;③ 在后台线程调 bench_run(bench_main.cc 的
// main 经 -Dmain=bench_run 改名同编,勿动 bench_main.cc);④ 跑完写 DONE 标记后退出。
//
// ⚠️ bench 必须在后台线程跑:主线程上跑几十秒会被 watchdog 杀死。
// ⚠️ 两个流共用同一个 fd(dup2),避免 "w"/"a" 两个独立 fd 互相覆写。

#import <UIKit/UIKit.h>
#include <cstdio>
#include <unistd.h>

int bench_run(int argc, char** argv);  // 同为 C++ 编译,mangling 一致,不要 extern "C"

@interface BenchAppDelegate : UIResponder <UIApplicationDelegate>
@property(strong, nonatomic) UIWindow* window;
@end

@implementation BenchAppDelegate
- (BOOL)application:(UIApplication*)app didFinishLaunchingWithOptions:(NSDictionary*)opts {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  UIViewController* vc = [UIViewController new];
  vc.view.backgroundColor = UIColor.blackColor;
  UILabel* lb = [[UILabel alloc] initWithFrame:vc.view.bounds];
  lb.text = @"CasDiffMVS bench 运行中…\n结果在 Documents/bench_result.txt";
  lb.numberOfLines = 0; lb.textAlignment = NSTextAlignmentCenter;
  lb.textColor = UIColor.whiteColor;
  [vc.view addSubview:lb];
  self.window.rootViewController = vc;
  [self.window makeKeyAndVisible];
  app.idleTimerDisabled = YES;  // 防锁屏中断打点

  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NSString* docs = NSSearchPathForDirectoriesInDomains(
        NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    NSString* outPath = [docs stringByAppendingPathComponent:@"bench_result.txt"];
    freopen(outPath.UTF8String, "w", stdout);
    setvbuf(stdout, NULL, _IONBF, 0);
    dup2(fileno(stdout), STDERR_FILENO);  // stderr 走同一 fd
    setvbuf(stderr, NULL, _IONBF, 0);

    NSBundle* b = NSBundle.mainBundle;
    NSString* model  = [b pathForResource:@"casdiffmvs_v5" ofType:@"onnx"];
    NSString* inputs = [b pathForResource:@"inputs8" ofType:@"bin"];
    if (!model || !inputs) { fprintf(stderr, "🔴 bundle 里找不到 model/inputs\n"); exit(2); }
    const char* ep = getenv("PW_BENCH_EP") ?: "1";  // 1=WebGPU(默认) 0=CPU
    char* argv2[] = {(char*)"casdiffbench", (char*)model.UTF8String,
                     (char*)inputs.UTF8String, (char*)ep, nullptr};
    int rc = bench_run(4, argv2);
    fflush(stdout); fflush(stderr);

    NSString* done = [NSString stringWithFormat:@"rc=%d\n", rc];
    [done writeToFile:[docs stringByAppendingPathComponent:@"DONE"]
           atomically:YES encoding:NSUTF8StringEncoding error:nil];
    exit(rc);  // bench_main.cc 失败路径自己 exit(1),那时没有 DONE = 没跑完
  });
  return YES;
}
@end

int main(int argc, char** argv) {
  @autoreleasepool {
    return UIApplicationMain(argc, argv, nil, NSStringFromClass([BenchAppDelegate class]));
  }
}
