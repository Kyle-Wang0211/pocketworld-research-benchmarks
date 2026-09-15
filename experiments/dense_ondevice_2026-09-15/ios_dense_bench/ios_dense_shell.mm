// iOS shell for the dense chain bench (same shape as the fusion-gate shell): stdout → Documents/bench_result.txt,
// dense_bench_run(bundle, Documents, PW_DENSE_FRAMES) on a background thread, DONE marker, exit.
#import <UIKit/UIKit.h>
#include <cstdio>
#include <cstdlib>
#include <unistd.h>

int dense_bench_run(int argc, char** argv);

@interface DenseAppDelegate : UIResponder <UIApplicationDelegate>
@property(strong, nonatomic) UIWindow* window;
@end
@implementation DenseAppDelegate
- (BOOL)application:(UIApplication*)app didFinishLaunchingWithOptions:(NSDictionary*)opts {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  UIViewController* vc = [UIViewController new]; vc.view.backgroundColor = UIColor.blackColor;
  UILabel* lb = [[UILabel alloc] initWithFrame:vc.view.bounds];
  lb.text = @"CasDiffMVS dense chain 运行中…\n结果在 Documents/bench_result.txt";
  lb.numberOfLines = 0; lb.textAlignment = NSTextAlignmentCenter; lb.textColor = UIColor.whiteColor;
  [vc.view addSubview:lb]; self.window.rootViewController = vc; [self.window makeKeyAndVisible];
  app.idleTimerDisabled = YES;
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NSString* docs = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    freopen([docs stringByAppendingPathComponent:@"bench_result.txt"].UTF8String, "w", stdout);
    setvbuf(stdout, NULL, _IONBF, 0); dup2(fileno(stdout), STDERR_FILENO); setvbuf(stderr, NULL, _IONBF, 0);
    NSString* bundle = [NSBundle.mainBundle pathForResource:@"dense_inputs" ofType:nil];
    if (!bundle) { fprintf(stderr, "🔴 bundle 里找不到 dense_inputs\n"); exit(2); }
    const char* frames = getenv("PW_DENSE_FRAMES") ?: "0-7";
    char* argv2[] = {(char*)"densebench", (char*)bundle.UTF8String, (char*)docs.UTF8String, (char*)frames, nullptr};
    int rc = dense_bench_run(4, argv2);
    fflush(stdout); fflush(stderr);
    [[NSString stringWithFormat:@"rc=%d\n", rc] writeToFile:[docs stringByAppendingPathComponent:@"DONE"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
    exit(rc);
  });
  return YES;
}
@end
int main(int argc, char** argv) { @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass([DenseAppDelegate class])); } }
