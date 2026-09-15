// iOS shell for the Stage-2 fusion device gate (adapted from casdiffmvs_wgsl_port bench/ios_shell_main.mm).
// ① stdout/stderr → Documents/bench_result.txt  ② argv = bundle subpack + Documents/fuse_out + digest flags
// ③ fuse_run (= test_fuse.cc main renamed via -Dmain=fuse_run) on a background thread  ④ DONE marker, exit.
#import <UIKit/UIKit.h>
#include <cstdio>
#include <cstdlib>
#include <unistd.h>

int fuse_run(int argc, char** argv);

@interface FuseAppDelegate : UIResponder <UIApplicationDelegate>
@property(strong, nonatomic) UIWindow* window;
@end

@implementation FuseAppDelegate
- (BOOL)application:(UIApplication*)app didFinishLaunchingWithOptions:(NSDictionary*)opts {
  self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
  UIViewController* vc = [UIViewController new];
  vc.view.backgroundColor = UIColor.blackColor;
  UILabel* lb = [[UILabel alloc] initWithFrame:vc.view.bounds];
  lb.text = @"CasDiffMVS fusion gate 运行中…\n结果在 Documents/bench_result.txt";
  lb.numberOfLines = 0; lb.textAlignment = NSTextAlignmentCenter; lb.textColor = UIColor.whiteColor;
  [vc.view addSubview:lb];
  self.window.rootViewController = vc;
  [self.window makeKeyAndVisible];
  app.idleTimerDisabled = YES;

  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NSString* docs = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    NSString* outPath = [docs stringByAppendingPathComponent:@"bench_result.txt"];
    freopen(outPath.UTF8String, "w", stdout);
    setvbuf(stdout, NULL, _IONBF, 0);
    dup2(fileno(stdout), STDERR_FILENO);
    setvbuf(stderr, NULL, _IONBF, 0);
    NSString* pack = [NSBundle.mainBundle pathForResource:@"subpack8" ofType:nil];
    if (!pack) { fprintf(stderr, "🔴 bundle 里找不到 subpack8\n"); exit(2); }
    NSString* out = [docs stringByAppendingPathComponent:@"fuse_out"];
    const char* frames = getenv("PW_FUSE_FRAMES") ?: "0-7";
    fprintf(stdout, "pack=%s frames=%s\n", pack.UTF8String, frames);
    char* argv2[] = {(char*)"fusebench", (char*)pack.UTF8String, (char*)out.UTF8String,
                     (char*)"--hash", (char*)"--no-dump", (char*)"--frames", (char*)frames, nullptr};
    int rc = fuse_run(7, argv2);
    fflush(stdout); fflush(stderr);
    NSString* done = [NSString stringWithFormat:@"rc=%d\n", rc];
    [done writeToFile:[docs stringByAppendingPathComponent:@"DONE"] atomically:YES encoding:NSUTF8StringEncoding error:nil];
    exit(rc);
  });
  return YES;
}
@end

int main(int argc, char** argv) {
  @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass([FuseAppDelegate class])); }
}
