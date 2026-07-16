#import "AppDelegate.h"

#import <CommonCrypto/CommonDigest.h>
#import <CoreML/CoreML.h>
#import <mach/mach.h>
#import <sys/sysctl.h>

#include "dkm_coreml_c_api.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <limits>
#include <string>

namespace {

constexpr NSUInteger kWarmRunCount = 10;
constexpr uint32_t kExpectedWidth = 512;
constexpr uint32_t kExpectedHeight = 288;
constexpr char kExpectedWeightSHA256[] =
    "b8bfd71c5850b8bac1e493760ac27fa9ff677cc7fce1cc0ceca66ec0577983dd";
constexpr char kReferenceFlowSHA256[] =
    "450422e88a690cc52b36d5bb4780223e6060fd14c09914c5d452c31d7430a8c7";
constexpr char kReferenceCertaintySHA256[] =
    "5025f9d3a683a6c04d712e2923462027cc742ac2c69fd0896c65c6c3f7f797ca";
constexpr char kReferenceLowCertaintySHA256[] =
    "e94c97ab9edd5e58d6365b8d89f25a8f6a2282687f60a43bc7fa132905b3afd1";

NSString* hexDigest(const unsigned char* digest) {
    NSMutableString* value = [NSMutableString stringWithCapacity:CC_SHA256_DIGEST_LENGTH * 2];
    for (NSUInteger index = 0; index < CC_SHA256_DIGEST_LENGTH; ++index) {
        [value appendFormat:@"%02x", digest[index]];
    }
    return value;
}

NSString* sha256Bytes(const void* bytes, size_t length) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(bytes, static_cast<CC_LONG>(length), digest);
    return hexDigest(digest);
}

NSString* sha256File(NSURL* url, NSError** error) {
    NSFileHandle* handle = [NSFileHandle fileHandleForReadingFromURL:url error:error];
    if (!handle) return nil;
    CC_SHA256_CTX context;
    CC_SHA256_Init(&context);
    while (true) {
        @autoreleasepool {
            NSData* chunk = [handle readDataOfLength:1024 * 1024];
            if (chunk.length == 0) break;
            CC_SHA256_Update(&context, chunk.bytes, static_cast<CC_LONG>(chunk.length));
        }
    }
    [handle closeFile];
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256_Final(digest, &context);
    return hexDigest(digest);
}

NSString* thermalStateName(NSProcessInfoThermalState state) {
    switch (state) {
        case NSProcessInfoThermalStateNominal: return @"nominal";
        case NSProcessInfoThermalStateFair: return @"fair";
        case NSProcessInfoThermalStateSerious: return @"serious";
        case NSProcessInfoThermalStateCritical: return @"critical";
    }
    return @"unknown";
}

uint64_t residentBytes() {
    mach_task_basic_info_data_t info{};
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    const kern_return_t result = task_info(
        mach_task_self(), MACH_TASK_BASIC_INFO,
        reinterpret_cast<task_info_t>(&info), &count);
    return result == KERN_SUCCESS ? info.resident_size : 0;
}

NSDictionary* stats(const float* values, size_t count) {
    if (!values || count == 0) return @{};
    double sum = 0.0;
    float minimum = std::numeric_limits<float>::infinity();
    float maximum = -std::numeric_limits<float>::infinity();
    size_t finiteCount = 0;
    for (size_t index = 0; index < count; ++index) {
        const float value = values[index];
        if (!std::isfinite(value)) continue;
        minimum = std::min(minimum, value);
        maximum = std::max(maximum, value);
        sum += value;
        ++finiteCount;
    }
    return @{
        @"count": @(count),
        @"finite_count": @(finiteCount),
        @"min": finiteCount ? @(minimum) : [NSNull null],
        @"max": finiteCount ? @(maximum) : [NSNull null],
        @"mean": finiteCount ? @(sum / finiteCount) : [NSNull null],
    };
}

NSString* machineIdentifier() {
    size_t size = 0;
    sysctlbyname("hw.machine", nullptr, &size, nullptr, 0);
    std::string value(size, '\0');
    sysctlbyname("hw.machine", value.data(), &size, nullptr, 0);
    if (!value.empty() && value.back() == '\0') value.pop_back();
    return [NSString stringWithUTF8String:value.c_str()];
}

}  // namespace

@interface AppDelegate ()

@property(nonatomic, strong) UITextView* statusView;

@end

@implementation AppDelegate

- (BOOL)application:(UIApplication*)application
    didFinishLaunchingWithOptions:(NSDictionary*)launchOptions {
    (void)launchOptions;
    application.idleTimerDisabled = YES;
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    UIViewController* controller = [[UIViewController alloc] init];
    controller.view.backgroundColor = UIColor.systemBackgroundColor;
    self.statusView = [[UITextView alloc] initWithFrame:CGRectZero];
    self.statusView.translatesAutoresizingMaskIntoConstraints = NO;
    self.statusView.editable = NO;
    self.statusView.font = [UIFont monospacedSystemFontOfSize:15 weight:UIFontWeightRegular];
    self.statusView.text = @"DKM Bench\nloading fixed 512×288 model…";
    [controller.view addSubview:self.statusView];
    [NSLayoutConstraint activateConstraints:@[
        [self.statusView.leadingAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.leadingAnchor constant:12],
        [self.statusView.trailingAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.trailingAnchor constant:-12],
        [self.statusView.topAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.topAnchor constant:12],
        [self.statusView.bottomAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.bottomAnchor constant:-12],
    ]];
    self.window.rootViewController = controller;
    [self.window makeKeyAndVisible];

    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        [self runBenchmark];
    });
    return YES;
}

- (void)setStatus:(NSString*)status {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.statusView.text = status;
    });
}

- (BOOL)writeJSON:(NSDictionary*)result toURL:(NSURL*)url error:(NSError**)error {
    NSData* data = [NSJSONSerialization dataWithJSONObject:result
                                                   options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys
                                                     error:error];
    return data && [data writeToURL:url options:NSDataWritingAtomic error:error];
}

- (void)runBenchmark {
    @autoreleasepool {
        NSBundle* bundle = NSBundle.mainBundle;
        NSURL* modelURL = [bundle URLForResource:@"DKMv3Outdoor512x288" withExtension:@"mlmodelc"];
        NSURL* image0URL = [bundle URLForResource:@"image0_nchw" withExtension:@"f32"];
        NSURL* image1URL = [bundle URLForResource:@"image1_nchw" withExtension:@"f32"];
        if (!modelURL || !image0URL || !image1URL) {
            [self finishWithError:@"bundled model or fixed input is missing"];
            return;
        }

        NSError* fileError = nil;
        NSData* image0 = [NSData dataWithContentsOfURL:image0URL options:NSDataReadingMappedIfSafe error:&fileError];
        NSData* image1 = [NSData dataWithContentsOfURL:image1URL options:NSDataReadingMappedIfSafe error:&fileError];
        const size_t expectedInputCount = static_cast<size_t>(3) * kExpectedHeight * kExpectedWidth;
        const size_t expectedBytes = expectedInputCount * sizeof(float);
        if (!image0 || !image1 || image0.length != expectedBytes || image1.length != expectedBytes) {
            [self finishWithError:[NSString stringWithFormat:@"fixed input load/size failure: %@", fileError ?: @"invalid byte count"]];
            return;
        }

        NSArray<NSURL*>* documents = [[NSFileManager defaultManager]
            URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask];
        NSURL* resultDirectory = [documents.firstObject URLByAppendingPathComponent:@"dkm_bench" isDirectory:YES];
        if (![[NSFileManager defaultManager] createDirectoryAtURL:resultDirectory
                                      withIntermediateDirectories:YES
                                                       attributes:nil
                                                            error:&fileError]) {
            [self finishWithError:[NSString stringWithFormat:@"result directory failure: %@", fileError]];
            return;
        }
        const long long startedMilliseconds = llround([[NSDate date] timeIntervalSince1970] * 1000.0);
        NSURL* runURL = [resultDirectory URLByAppendingPathComponent:
            [NSString stringWithFormat:@"run_%lld.json", startedMilliseconds]];
        NSURL* latestURL = [resultDirectory URLByAppendingPathComponent:@"latest.json"];
        NSURL* partialURL = [resultDirectory URLByAppendingPathComponent:@"latest.partial.json"];

        NSMutableDictionary* report = [@{
            @"schema_version": @1,
            @"status": @"running",
            @"started_unix_ms": @(startedMilliseconds),
            @"bundle_identifier": NSBundle.mainBundle.bundleIdentifier ?: @"",
            @"bundle_version": [bundle objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"",
            @"device_model": machineIdentifier() ?: @"unknown",
            @"os_version": UIDevice.currentDevice.systemVersion,
            @"input_width": @(kExpectedWidth),
            @"input_height": @(kExpectedHeight),
            @"compute_units": @"cpu_and_gpu",
            @"precision": @"float32_mlprogram",
            @"warm_run_target": @(kWarmRunCount),
            @"model_weight_expected_sha256": [NSString stringWithUTF8String:kExpectedWeightSHA256],
            @"input0_sha256": sha256Bytes(image0.bytes, image0.length),
            @"input1_sha256": sha256Bytes(image1.bytes, image1.length),
            @"runs": [NSMutableArray array],
        } mutableCopy];

        char errorMessage[1024] = {};
        pw_dkm_coreml_context* context = nullptr;
        const auto loadStarted = std::chrono::steady_clock::now();
        const int createStatus = pw_dkm_coreml_create(
            modelURL.fileSystemRepresentation, &context, errorMessage, sizeof(errorMessage));
        const auto loadFinished = std::chrono::steady_clock::now();
        report[@"model_load_seconds"] = @(
            std::chrono::duration<double>(loadFinished - loadStarted).count());
        if (createStatus != 0 || !context) {
            report[@"status"] = @"failed";
            report[@"error"] = [NSString stringWithFormat:@"model create %d: %s", createStatus, errorMessage];
            [self writeJSON:report toURL:partialURL error:nil];
            [self finishWithError:report[@"error"]];
            return;
        }
        if (pw_dkm_coreml_input_width(context) != kExpectedWidth ||
            pw_dkm_coreml_input_height(context) != kExpectedHeight) {
            pw_dkm_coreml_destroy(context);
            [self finishWithError:@"model input dimensions do not match 512×288 contract"];
            return;
        }

        NSMutableArray* runs = report[@"runs"];
        BOOL failed = NO;
        for (NSUInteger index = 0; index <= kWarmRunCount; ++index) {
            @autoreleasepool {
                [self setStatus:[NSString stringWithFormat:
                    @"DKM Bench\n%@ run %lu/%lu\nthermal: %@",
                    index == 0 ? @"cold" : @"warm",
                    (unsigned long)(index == 0 ? 1 : index),
                    (unsigned long)(index == 0 ? 1 : kWarmRunCount),
                    thermalStateName(NSProcessInfo.processInfo.thermalState)]];
                const NSString* thermalBefore = thermalStateName(NSProcessInfo.processInfo.thermalState);
                const uint64_t rssBefore = residentBytes();
                pw_dkm_coreml_result output{};
                std::memset(errorMessage, 0, sizeof(errorMessage));
                const auto wallStarted = std::chrono::steady_clock::now();
                const int predictStatus = pw_dkm_coreml_predict(
                    context,
                    static_cast<const float*>(image0.bytes),
                    static_cast<const float*>(image1.bytes),
                    expectedInputCount,
                    &output,
                    errorMessage,
                    sizeof(errorMessage));
                const auto wallFinished = std::chrono::steady_clock::now();
                NSMutableDictionary* run = [@{
                    @"index": @(index),
                    @"kind": index == 0 ? @"cold" : @"warm",
                    @"thermal_before": thermalBefore,
                    @"thermal_after": thermalStateName(NSProcessInfo.processInfo.thermalState),
                    @"rss_before_bytes": @(rssBefore),
                    @"rss_after_bytes": @(residentBytes()),
                    @"call_wall_seconds": @(
                        std::chrono::duration<double>(wallFinished - wallStarted).count()),
                    @"coreml_prediction_seconds": @(output.inference_seconds),
                    @"status_code": @(predictStatus),
                } mutableCopy];
                if (predictStatus != 0) {
                    run[@"error"] = [NSString stringWithUTF8String:errorMessage];
                    failed = YES;
                } else {
                    NSString* flowSHA = sha256Bytes(output.flow, output.flow_count * sizeof(float));
                    NSString* certaintySHA = sha256Bytes(
                        output.certainty, output.certainty_count * sizeof(float));
                    NSString* lowCertaintySHA = sha256Bytes(
                        output.low_certainty, output.low_certainty_count * sizeof(float));
                    run[@"flow_sha256"] = flowSHA;
                    run[@"certainty_sha256"] = certaintySHA;
                    run[@"low_certainty_sha256"] = lowCertaintySHA;
                    run[@"flow_matches_host_reference"] = @([flowSHA isEqualToString:
                        [NSString stringWithUTF8String:kReferenceFlowSHA256]]);
                    run[@"certainty_matches_host_reference"] = @([certaintySHA isEqualToString:
                        [NSString stringWithUTF8String:kReferenceCertaintySHA256]]);
                    run[@"low_certainty_matches_host_reference"] = @([lowCertaintySHA isEqualToString:
                        [NSString stringWithUTF8String:kReferenceLowCertaintySHA256]]);
                    run[@"flow_stats"] = stats(output.flow, output.flow_count);
                    run[@"certainty_stats"] = stats(output.certainty, output.certainty_count);
                    run[@"low_certainty_stats"] = stats(output.low_certainty, output.low_certainty_count);
                    if (index == 0) {
                        NSDictionary<NSString*, NSData*>* coldOutputs = @{
                            @"cold_flow.f32": [NSData dataWithBytes:output.flow
                                                              length:output.flow_count * sizeof(float)],
                            @"cold_certainty.f32": [NSData dataWithBytes:output.certainty
                                                                   length:output.certainty_count * sizeof(float)],
                            @"cold_low_certainty.f32": [NSData dataWithBytes:output.low_certainty
                                                                       length:output.low_certainty_count * sizeof(float)],
                        };
                        NSMutableDictionary* outputFiles = [NSMutableDictionary dictionary];
                        for (NSString* filename in coldOutputs) {
                            NSURL* outputURL = [resultDirectory URLByAppendingPathComponent:filename];
                            NSError* outputWriteError = nil;
                            const BOOL wrote = [coldOutputs[filename] writeToURL:outputURL
                                                                         options:NSDataWritingAtomic
                                                                           error:&outputWriteError];
                            outputFiles[filename] = @{
                                @"bytes": @(coldOutputs[filename].length),
                                @"sha256": sha256Bytes(
                                    coldOutputs[filename].bytes, coldOutputs[filename].length),
                                @"written": @(wrote),
                                @"error": outputWriteError.localizedDescription ?: @"",
                            };
                        }
                        report[@"cold_output_files"] = outputFiles;
                    }
                }
                [runs addObject:run];
                pw_dkm_coreml_result_release(&output);
                report[@"completed_run_count"] = @(runs.count);
                [self writeJSON:report toURL:partialURL error:nil];
                if (failed) break;
            }
        }
        pw_dkm_coreml_destroy(context);

        NSURL* weightURL = [modelURL URLByAppendingPathComponent:@"weights/weight.bin"];
        NSString* actualWeightSHA = sha256File(weightURL, &fileError);
        report[@"model_weight_actual_sha256"] = actualWeightSHA ?: [NSNull null];
        report[@"model_weight_hash_matches"] = @(
            actualWeightSHA && [actualWeightSHA isEqualToString:
                [NSString stringWithUTF8String:kExpectedWeightSHA256]]);
        report[@"finished_unix_ms"] = @(llround([[NSDate date] timeIntervalSince1970] * 1000.0));
        report[@"final_thermal_state"] = thermalStateName(NSProcessInfo.processInfo.thermalState);
        report[@"final_rss_bytes"] = @(residentBytes());
        report[@"status"] = failed ? @"failed" : @"complete";
        if (fileError) report[@"model_hash_error"] = fileError.localizedDescription;
        NSError* writeError = nil;
        if (![self writeJSON:report toURL:runURL error:&writeError] ||
            ![self writeJSON:report toURL:latestURL error:&writeError]) {
            [self finishWithError:[NSString stringWithFormat:@"final JSON write failure: %@", writeError]];
            return;
        }
        [[NSFileManager defaultManager] removeItemAtURL:partialURL error:nil];

        NSMutableArray<NSNumber*>* warm = [NSMutableArray array];
        for (NSDictionary* run in runs) {
            if ([run[@"kind"] isEqual:@"warm"] && [run[@"status_code"] integerValue] == 0) {
                [warm addObject:run[@"coreml_prediction_seconds"]];
            }
        }
        NSArray<NSNumber*>* sorted = [warm sortedArrayUsingSelector:@selector(compare:)];
        NSNumber* median = sorted.count ? sorted[sorted.count / 2] : @0;
        NSDictionary* cold = runs.firstObject;
        [self setStatus:[NSString stringWithFormat:
            @"DKM Bench COMPLETE\n\nmodel load: %.3f s\ncold: %.3f s\nwarm median: %.3f s\nthermal: %@\nruns: %lu\nmodel hash: %@\n\n%@",
            [report[@"model_load_seconds"] doubleValue],
            [cold[@"coreml_prediction_seconds"] doubleValue],
            median.doubleValue,
            report[@"final_thermal_state"],
            (unsigned long)runs.count,
            [report[@"model_weight_hash_matches"] boolValue] ? @"PASS" : @"FAIL",
            latestURL.path]];
    }
}

- (void)finishWithError:(NSString*)message {
    [self setStatus:[NSString stringWithFormat:@"DKM Bench FAILED\n\n%@", message]];
}

@end
