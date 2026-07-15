#import "AppDelegate.h"

#import <CommonCrypto/CommonDigest.h>
#import <Metal/Metal.h>
#import <mach/mach.h>
#import <simd/simd.h>
#import <sys/sysctl.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>

#include "portable_depth_contract.h"

namespace {

// One full kernel pass is the frozen diagnostic.  Repetition belongs in the
// optimized tiled kernel; repeating this deliberately naive baseline only
// heats the device without adding a new correctness observation.
constexpr NSUInteger kRunCount = 1;

struct MetalParams {
    std::uint32_t width;
    std::uint32_t height;
    std::uint32_t pixelCount;
    std::uint32_t depthCount;
    std::uint32_t sourceCount;
    std::uint32_t patchN;
    std::uint32_t minViews;
    std::uint32_t exclusionRadius;
    float minStdU8;
    float nccMin;
    float depthMargin;
    float inverseDepthFirst;
    float inverseDepthStep;
    float padding0;
    float padding1;
    float padding2;
    simd_float4 inverseK0;
    simd_float4 inverseK1;
    simd_float4 inverseK2;
};

static_assert(sizeof(MetalParams) == 112, "Metal parameter layout changed");

NSString* const kShaderSource = @R"METAL(
#include <metal_stdlib>
using namespace metal;

struct Params {
    uint width;
    uint height;
    uint pixel_count;
    uint depth_count;
    uint source_count;
    uint patch_n;
    uint min_views;
    uint exclusion_radius;
    float min_std_u8;
    float ncc_min;
    float depth_margin;
    float inverse_depth_first;
    float inverse_depth_step;
    float padding0;
    float padding1;
    float padding2;
    float4 inverse_k0;
    float4 inverse_k1;
    float4 inverse_k2;
};

inline float read_constant(
    device const float* image, uint width, uint height, int x, int y) {
    if (x < 0 || y < 0 || x >= int(width) || y >= int(height)) return 0.0f;
    return image[uint(y) * width + uint(x)];
}

inline float sample_bilinear_constant(
    device const float* image, uint width, uint height, float x, float y) {
    // OpenCV INTER_LINEAR uses a 5-bit interpolation table.  Quantizing here
    // makes point-birth decisions deterministic across the host reference,
    // Metal, and future Vulkan/WebGPU implementations.
    x = rint(x * 32.0f) / 32.0f;
    y = rint(y * 32.0f) / 32.0f;
    const int x0 = int(floor(x));
    const int y0 = int(floor(y));
    const int x1 = x0 + 1;
    const int y1 = y0 + 1;
    const float wx = x - float(x0);
    const float wy = y - float(y0);
    const float top = mix(
        read_constant(image, width, height, x0, y0),
        read_constant(image, width, height, x1, y0), wx);
    const float bottom = mix(
        read_constant(image, width, height, x0, y1),
        read_constant(image, width, height, x1, y1), wx);
    return mix(top, bottom, wy);
}

inline int reflect101(int coordinate, int length) {
    if (length <= 1) return 0;
    int value = coordinate;
    while (value < 0 || value >= length) {
        value = value < 0 ? -value : 2 * length - value - 2;
    }
    return value;
}

inline float3 reference_ray(constant Params& params, float x, float y) {
    const float4 pixel = float4(x, y, 1.0f, 0.0f);
    return float3(
        dot(params.inverse_k0, pixel),
        dot(params.inverse_k1, pixel),
        dot(params.inverse_k2, pixel));
}

kernel void known_pose_depth_sweep(
    device const float* gray_frames [[buffer(0)]],
    device const float4* source_projections [[buffer(1)]],
    constant Params& params [[buffer(2)]],
    device ushort* best_index_output [[buffer(3)]],
    device float* best_score_output [[buffer(4)]],
    device float* second_score_output [[buffer(5)]],
    device uchar* views_output [[buffer(6)]],
    device uchar* accepted_output [[buffer(7)]],
    uint gid [[thread_position_in_grid]]) {
    if (gid >= params.pixel_count) return;
    constexpr uint kMaxPatchSamples = 25;
    constexpr uint kMaxDepths = 64;
    constexpr uint kMaxSources = 8;
    float costs[kMaxDepths];
    uchar depth_views[kMaxDepths];
    const uint x = gid % params.width;
    const uint y = gid / params.width;
    const uint half_patch = params.patch_n / 2;
    if (params.patch_n * params.patch_n > kMaxPatchSamples ||
        params.depth_count > kMaxDepths || params.source_count > kMaxSources ||
        params.patch_n == 0) {
        best_index_output[gid] = 0;
        best_score_output[gid] = -2.0f;
        second_score_output[gid] = -2.0f;
        views_output[gid] = 0;
        accepted_output[gid] = 0;
        return;
    }

    float reference_patch[kMaxPatchSamples];
    float reference_sum = 0.0f;
    uint sample_index = 0;
    for (int dy = -int(half_patch); dy <= int(half_patch); ++dy) {
        for (int dx = -int(half_patch); dx <= int(half_patch); ++dx) {
            const int reflected_x = reflect101(int(x) + dx, int(params.width));
            const int reflected_y = reflect101(int(y) + dy, int(params.height));
            const float value = gray_frames[
                uint(reflected_y) * params.width + uint(reflected_x)];
            reference_patch[sample_index++] = value;
            reference_sum += value;
        }
    }
    const float area = float(sample_index);
    const float reference_mean = reference_sum / area;
    float reference_variance = 0.0f;
    for (uint index = 0; index < sample_index; ++index) {
        const float centered = reference_patch[index] - reference_mean;
        reference_variance += centered * centered;
    }
    if (sqrt(reference_variance / area) < params.min_std_u8) {
        best_index_output[gid] = 0;
        best_score_output[gid] = -2.0f;
        second_score_output[gid] = -2.0f;
        views_output[gid] = 0;
        accepted_output[gid] = 0;
        return;
    }

    const float center_margin = float(half_patch + 1);
    for (uint depth_index = 0; depth_index < params.depth_count; ++depth_index) {
        const float inverse_depth = params.inverse_depth_first +
            float(depth_index) * params.inverse_depth_step;
        const float depth = 1.0f / inverse_depth;
        float top_scores[kMaxSources];
        for (uint index = 0; index < kMaxSources; ++index) top_scores[index] = -2.0f;
        uint valid_count = 0;
        for (uint source = 0; source < params.source_count; ++source) {
            device const float4* projection = source_projections + source * 3;
            const float3 center_ray = reference_ray(params, float(x), float(y));
            const float4 center = float4(center_ray * depth, 1.0f);
            const float center_z = dot(projection[2], center);
            if (center_z <= 0.05f) continue;
            const float center_x = dot(projection[0], center) / center_z;
            const float center_y = dot(projection[1], center) / center_z;
            if (center_x < center_margin || center_x >= float(params.width) - center_margin ||
                center_y < center_margin || center_y >= float(params.height) - center_margin) continue;

            float source_patch[kMaxPatchSamples];
            float source_sum = 0.0f;
            uint index = 0;
            device const float* source_image = gray_frames + (source + 1) * params.pixel_count;
            for (int dy = -int(half_patch); dy <= int(half_patch); ++dy) {
                for (int dx = -int(half_patch); dx <= int(half_patch); ++dx) {
                    const int reflected_x = reflect101(int(x) + dx, int(params.width));
                    const int reflected_y = reflect101(int(y) + dy, int(params.height));
                    const float3 ray = reference_ray(
                        params, float(reflected_x), float(reflected_y));
                    const float4 point = float4(ray * depth, 1.0f);
                    const float z = dot(projection[2], point);
                    const float denominator = z > 1.0e-12f ? z : 1.0f;
                    const float projected_x = dot(projection[0], point) / denominator;
                    const float projected_y = dot(projection[1], point) / denominator;
                    const float value = sample_bilinear_constant(
                        source_image, params.width, params.height, projected_x, projected_y);
                    source_patch[index++] = value;
                    source_sum += value;
                }
            }
            if (index != sample_index) continue;
            const float source_mean = source_sum / area;
            float source_variance = 0.0f;
            float covariance = 0.0f;
            for (uint patch_index = 0; patch_index < sample_index; ++patch_index) {
                const float reference_centered = reference_patch[patch_index] - reference_mean;
                const float source_centered = source_patch[patch_index] - source_mean;
                source_variance += source_centered * source_centered;
                covariance += reference_centered * source_centered;
            }
            if (sqrt(source_variance / area) < params.min_std_u8) continue;
            const float score = covariance /
                (sqrt(reference_variance * source_variance) + 1.0e-6f);
            ++valid_count;
            for (uint slot = 0; slot < params.min_views; ++slot) {
                if (score <= top_scores[slot]) continue;
                for (uint shift = params.min_views - 1; shift > slot; --shift) {
                    top_scores[shift] = top_scores[shift - 1];
                }
                top_scores[slot] = score;
                break;
            }
        }
        float cost = -2.0f;
        if (valid_count >= params.min_views) {
            cost = 0.0f;
            for (uint index = 0; index < params.min_views; ++index) cost += top_scores[index];
            cost /= float(params.min_views);
        }
        costs[depth_index] = cost;
        depth_views[depth_index] = uchar(valid_count);
    }

    uint best_index = 0;
    float best_score = costs[0];
    for (uint index = 1; index < params.depth_count; ++index) {
        if (costs[index] > best_score) {
            best_score = costs[index];
            best_index = index;
        }
    }
    float second_score = -2.0f;
    for (uint index = 0; index < params.depth_count; ++index) {
        const int delta = int(index) - int(best_index);
        if (abs(delta) <= int(params.exclusion_radius)) continue;
        second_score = max(second_score, costs[index]);
    }
    const uchar views = depth_views[best_index];
    best_index_output[gid] = ushort(best_index);
    best_score_output[gid] = best_score;
    second_score_output[gid] = second_score;
    views_output[gid] = views;
    accepted_output[gid] = uchar(
        best_score >= params.ncc_min &&
        best_score - second_score >= params.depth_margin &&
        uint(views) >= params.min_views);
}
)METAL";

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

NSString* machineIdentifier() {
    size_t size = 0;
    sysctlbyname("hw.machine", nullptr, &size, nullptr, 0);
    std::string value(size, '\0');
    sysctlbyname("hw.machine", value.data(), &size, nullptr, 0);
    if (!value.empty() && value.back() == '\0') value.pop_back();
    return [NSString stringWithUTF8String:value.c_str()];
}

NSString* sha256(NSData* data) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data.bytes, static_cast<CC_LONG>(data.length), digest);
    NSMutableString* result = [NSMutableString stringWithCapacity:CC_SHA256_DIGEST_LENGTH * 2];
    for (NSUInteger index = 0; index < CC_SHA256_DIGEST_LENGTH; ++index) {
        [result appendFormat:@"%02x", digest[index]];
    }
    return result;
}

NSURL* resourceURL(NSString* filename) {
    return [NSBundle.mainBundle URLForResource:filename.stringByDeletingPathExtension
                                 withExtension:filename.pathExtension];
}

NSData* loadResource(NSString* filename, NSError** error) {
    NSURL* url = resourceURL(filename);
    return url ? [NSData dataWithContentsOfURL:url options:NSDataReadingMappedIfSafe error:error] : nil;
}

simd_float4 matrixRow(NSArray<NSNumber*>* values, NSUInteger start) {
    return simd_make_float4(
        values[start].floatValue, values[start + 1].floatValue,
        values[start + 2].floatValue, 0.0f);
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
    self.statusView.font = [UIFont monospacedSystemFontOfSize:14 weight:UIFontWeightRegular];
    self.statusView.text = @"PW Detector-Free Bench\nloading model-free cap56 fixture…";
    [controller.view addSubview:self.statusView];
    [NSLayoutConstraint activateConstraints:@[
        [self.statusView.leadingAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.leadingAnchor constant:12],
        [self.statusView.trailingAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.trailingAnchor constant:-12],
        [self.statusView.topAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.topAnchor constant:12],
        [self.statusView.bottomAnchor constraintEqualToAnchor:controller.view.safeAreaLayoutGuide.bottomAnchor constant:-12],
    ]];
    self.window.rootViewController = controller;
    [self.window makeKeyAndVisible];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ [self runBenchmark]; });
    return YES;
}

- (void)setStatus:(NSString*)status {
    dispatch_async(dispatch_get_main_queue(), ^{ self.statusView.text = status; });
}

- (void)fail:(NSString*)message {
    NSError* error = nil;
    NSArray<NSURL*>* documents = [[NSFileManager defaultManager]
        URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask];
    NSURL* directory = [documents.firstObject URLByAppendingPathComponent:@"detector_free_bench" isDirectory:YES];
    [[NSFileManager defaultManager] createDirectoryAtURL:directory
                            withIntermediateDirectories:YES attributes:nil error:&error];
    NSURL* latestURL = [directory URLByAppendingPathComponent:@"latest.json"];
    NSDictionary* report = @{
        @"schema": @"pocketworld_model_free_depth_sweep_a16_bench_v2",
        @"status": @"failed",
        @"decision": @"FAIL_A16_BENCH_RUNTIME",
        @"error": message ?: @"unknown",
        @"device_model": machineIdentifier() ?: @"unknown",
        @"os_version": UIDevice.currentDevice.systemVersion,
        @"thermal_final": thermalStateName(NSProcessInfo.processInfo.thermalState),
    };
    NSData* reportData = [NSJSONSerialization dataWithJSONObject:report
        options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
    [reportData writeToURL:latestURL options:NSDataWritingAtomic error:&error];
    [self setStatus:[NSString stringWithFormat:@"PW Detector-Free Bench FAILED\n\n%@", message]];
}

- (void)runBenchmark {
    @autoreleasepool {
        NSError* error = nil;
        NSURL* manifestURL = [NSBundle.mainBundle URLForResource:@"fixture_manifest" withExtension:@"json"];
        NSData* manifestData = manifestURL ? [NSData dataWithContentsOfURL:manifestURL options:0 error:&error] : nil;
        NSDictionary* manifest = manifestData ?
            [NSJSONSerialization JSONObjectWithData:manifestData options:0 error:&error] : nil;
        if (!manifest) {
            [self fail:[NSString stringWithFormat:@"manifest failed: %@", error]];
            return;
        }
        NSDictionary* contract = manifest[@"contract"];
        NSDictionary* geometry = manifest[@"geometry"];
        NSDictionary* resources = manifest[@"resources"];
        NSDictionary* registeredThresholds = manifest[@"registered_thresholds"];
        NSData* grayData = loadResource(resources[@"gray_frames.f32"][@"file"], &error);
        NSData* projectionData = loadResource(resources[@"source_projections.f32"][@"file"], &error);
        NSData* expectedBestIndexData = loadResource(resources[@"expected_best_index.u16"][@"file"], &error);
        NSData* expectedBestScoreData = loadResource(resources[@"expected_best_score.f32"][@"file"], &error);
        NSData* expectedSecondScoreData = loadResource(resources[@"expected_second_score.f32"][@"file"], &error);
        NSData* expectedViewsData = loadResource(resources[@"expected_views.u8"][@"file"], &error);
        NSData* expectedAcceptedData = loadResource(resources[@"expected_accepted.u8"][@"file"], &error);
        if (!grayData || !projectionData || !expectedBestIndexData || !expectedBestScoreData ||
            !expectedSecondScoreData || !expectedViewsData || !expectedAcceptedData) {
            [self fail:[NSString stringWithFormat:@"fixture resource failed: %@", error]];
            return;
        }

        MetalParams params{};
        params.width = [contract[@"width"] unsignedIntValue];
        params.height = [contract[@"height"] unsignedIntValue];
        params.pixelCount = params.width * params.height;
        params.depthCount = [contract[@"depth_samples"] unsignedIntValue];
        params.sourceCount = [contract[@"source_count"] unsignedIntValue];
        params.patchN = [contract[@"patch_n"] unsignedIntValue];
        params.minViews = [contract[@"min_views"] unsignedIntValue];
        params.exclusionRadius = [contract[@"peak_exclusion_radius_samples"] unsignedIntValue];
        params.minStdU8 = [contract[@"min_std_u8"] floatValue];
        params.nccMin = [contract[@"ncc_min"] floatValue];
        params.depthMargin = [contract[@"depth_margin"] floatValue];
        params.inverseDepthFirst = [geometry[@"inverse_depth_first"] floatValue];
        params.inverseDepthStep = [geometry[@"inverse_depth_step"] floatValue];
        NSArray<NSNumber*>* inverseK = geometry[@"reference_inverse_k_row_major_f32"];
        params.inverseK0 = matrixRow(inverseK, 0);
        params.inverseK1 = matrixRow(inverseK, 3);
        params.inverseK2 = matrixRow(inverseK, 6);

        const NSUInteger expectedGrayBytes =
            (params.sourceCount + 1) * params.pixelCount * sizeof(float);
        if (grayData.length != expectedGrayBytes ||
            projectionData.length != params.sourceCount * 12 * sizeof(float) ||
            expectedBestIndexData.length != params.pixelCount * sizeof(std::uint16_t) ||
            expectedBestScoreData.length != params.pixelCount * sizeof(float) ||
            expectedSecondScoreData.length != params.pixelCount * sizeof(float) ||
            expectedViewsData.length != params.pixelCount ||
            expectedAcceptedData.length != params.pixelCount) {
            [self fail:@"fixture byte count mismatch"];
            return;
        }

        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        id<MTLCommandQueue> queue = [device newCommandQueue];
        const auto compileStarted = std::chrono::steady_clock::now();
        id<MTLLibrary> library = [device newLibraryWithSource:kShaderSource options:nil error:&error];
        id<MTLFunction> function = [library newFunctionWithName:@"known_pose_depth_sweep"];
        id<MTLComputePipelineState> pipeline = function ?
            [device newComputePipelineStateWithFunction:function error:&error] : nil;
        const double compileSeconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - compileStarted).count();
        if (!device || !queue || !pipeline) {
            [self fail:[NSString stringWithFormat:@"Metal compile failed: %@", error]];
            return;
        }

        id<MTLBuffer> grayBuffer = [device newBufferWithBytes:grayData.bytes
                                                       length:grayData.length
                                                      options:MTLResourceStorageModeShared];
        id<MTLBuffer> projectionBuffer = [device newBufferWithBytes:projectionData.bytes
                                                             length:projectionData.length
                                                            options:MTLResourceStorageModeShared];
        id<MTLBuffer> bestIndexBuffer = [device newBufferWithLength:params.pixelCount * sizeof(std::uint16_t)
                                                            options:MTLResourceStorageModeShared];
        id<MTLBuffer> bestScoreBuffer = [device newBufferWithLength:params.pixelCount * sizeof(float)
                                                            options:MTLResourceStorageModeShared];
        id<MTLBuffer> secondScoreBuffer = [device newBufferWithLength:params.pixelCount * sizeof(float)
                                                              options:MTLResourceStorageModeShared];
        id<MTLBuffer> viewsBuffer = [device newBufferWithLength:params.pixelCount
                                                       options:MTLResourceStorageModeShared];
        id<MTLBuffer> acceptedBuffer = [device newBufferWithLength:params.pixelCount
                                                          options:MTLResourceStorageModeShared];

        NSMutableArray* runs = [NSMutableArray array];
        uint64_t peakRSS = residentBytes();
        for (NSUInteger runIndex = 0; runIndex < kRunCount; ++runIndex) {
            const auto started = std::chrono::steady_clock::now();
            id<MTLCommandBuffer> command = [queue commandBuffer];
            id<MTLComputeCommandEncoder> encoder = [command computeCommandEncoder];
            [encoder setComputePipelineState:pipeline];
            [encoder setBuffer:grayBuffer offset:0 atIndex:0];
            [encoder setBuffer:projectionBuffer offset:0 atIndex:1];
            [encoder setBytes:&params length:sizeof(params) atIndex:2];
            [encoder setBuffer:bestIndexBuffer offset:0 atIndex:3];
            [encoder setBuffer:bestScoreBuffer offset:0 atIndex:4];
            [encoder setBuffer:secondScoreBuffer offset:0 atIndex:5];
            [encoder setBuffer:viewsBuffer offset:0 atIndex:6];
            [encoder setBuffer:acceptedBuffer offset:0 atIndex:7];
            const NSUInteger threadWidth = std::min<NSUInteger>(
                pipeline.maxTotalThreadsPerThreadgroup, 64);
            [encoder dispatchThreads:MTLSizeMake(params.pixelCount, 1, 1)
                threadsPerThreadgroup:MTLSizeMake(threadWidth, 1, 1)];
            [encoder endEncoding];
            [command commit];
            [command waitUntilCompleted];
            const double wallSeconds = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - started).count();
            if (command.status != MTLCommandBufferStatusCompleted) {
                [self fail:[NSString stringWithFormat:@"GPU command failed: %@", command.error]];
                return;
            }
            peakRSS = std::max(peakRSS, residentBytes());
            const double gpuSeconds = command.GPUEndTime > command.GPUStartTime ?
                command.GPUEndTime - command.GPUStartTime : 0.0;
            [runs addObject:@{
                @"index": @(runIndex),
                @"kind": runIndex == 0 ? @"cold" : @"warm",
                @"wall_seconds": @(wallSeconds),
                @"gpu_seconds": @(gpuSeconds),
                @"rss_after_bytes": @(residentBytes()),
                @"thermal_after": thermalStateName(NSProcessInfo.processInfo.thermalState),
            }];
            [self setStatus:[NSString stringWithFormat:
                @"PW Detector-Free Bench\nrun %lu/%lu complete\nwall %.1f ms · GPU %.1f ms\nRSS %.1f MB · thermal %@",
                (unsigned long)(runIndex + 1), (unsigned long)kRunCount,
                wallSeconds * 1000.0, gpuSeconds * 1000.0,
                residentBytes() / 1048576.0,
                thermalStateName(NSProcessInfo.processInfo.thermalState)]];
        }

        const std::uint16_t* actualBestIndex = static_cast<const std::uint16_t*>(bestIndexBuffer.contents);
        const float* actualBestScore = static_cast<const float*>(bestScoreBuffer.contents);
        const float* actualSecondScore = static_cast<const float*>(secondScoreBuffer.contents);
        const std::uint8_t* actualViews = static_cast<const std::uint8_t*>(viewsBuffer.contents);
        const std::uint8_t* actualAccepted = static_cast<const std::uint8_t*>(acceptedBuffer.contents);
        const std::uint16_t* expectedBestIndex = static_cast<const std::uint16_t*>(expectedBestIndexData.bytes);
        const float* expectedBestScore = static_cast<const float*>(expectedBestScoreData.bytes);
        const float* expectedSecondScore = static_cast<const float*>(expectedSecondScoreData.bytes);
        const std::uint8_t* expectedViews = static_cast<const std::uint8_t*>(expectedViewsData.bytes);
        const std::uint8_t* expectedAccepted = static_cast<const std::uint8_t*>(expectedAcceptedData.bytes);
        NSArray<NSURL*>* documents = [[NSFileManager defaultManager]
            URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask];
        NSURL* directory = [documents.firstObject URLByAppendingPathComponent:@"detector_free_bench" isDirectory:YES];
        [[NSFileManager defaultManager] createDirectoryAtURL:directory
                                withIntermediateDirectories:YES attributes:nil error:&error];
        NSDictionary<NSString*, NSData*>* rawOutputs = @{
            @"actual_best_index.u16": [NSData dataWithBytes:actualBestIndex length:bestIndexBuffer.length],
            @"actual_best_score.f32": [NSData dataWithBytes:actualBestScore length:bestScoreBuffer.length],
            @"actual_second_score.f32": [NSData dataWithBytes:actualSecondScore length:secondScoreBuffer.length],
            @"actual_views.u8": [NSData dataWithBytes:actualViews length:viewsBuffer.length],
            @"actual_accepted.u8": [NSData dataWithBytes:actualAccepted length:acceptedBuffer.length],
        };
        for (NSString* filename in rawOutputs) {
            [rawOutputs[filename] writeToURL:[directory URLByAppendingPathComponent:filename]
                                     options:NSDataWritingAtomic error:&error];
        }
        const auto parity = pocketworld::depth_sweep::evaluate_parity(
            params.pixelCount,
            expectedBestIndex, expectedBestScore, expectedSecondScore,
            expectedViews, expectedAccepted,
            actualBestIndex, actualBestScore, actualSecondScore,
            actualViews, actualAccepted);
        pocketworld::depth_sweep::ParityThresholds parityThresholds;
        parityThresholds.valid_mismatch_max =
            [registeredThresholds[@"valid_mismatch_max"] unsignedLongValue];
        parityThresholds.accepted_mismatch_max =
            [registeredThresholds[@"accepted_mismatch_max"] unsignedLongValue];
        parityThresholds.accepted_best_index_mismatch_max =
            [registeredThresholds[@"accepted_best_index_mismatch_max"] unsignedLongValue];
        parityThresholds.views_mismatch_max =
            [registeredThresholds[@"views_mismatch_max"] unsignedLongValue];
        parityThresholds.score_mean_abs_max =
            [registeredThresholds[@"score_mean_abs_max"] doubleValue];
        parityThresholds.score_max_abs_max =
            [registeredThresholds[@"score_max_abs_max"] doubleValue];
        const BOOL parityPass = parity.passes(parityThresholds);

        NSURL* latestURL = [directory URLByAppendingPathComponent:@"latest.json"];
        NSDictionary* report = @{
            @"schema": @"pocketworld_model_free_depth_sweep_a16_bench_v2",
            @"status": parityPass ? @"complete" : @"failed",
            @"decision": parityPass ? @"PASS_A16_MODEL_FREE_DEPTH_SWEEP_PARITY" : @"FAIL_A16_MODEL_FREE_DEPTH_SWEEP_PARITY",
            @"device_model": machineIdentifier() ?: @"unknown",
            @"os_version": UIDevice.currentDevice.systemVersion,
            @"metal_device": device.name ?: @"unknown",
            @"manifest_sha256": sha256(manifestData),
            @"compile_seconds": @(compileSeconds),
            @"thermal_final": thermalStateName(NSProcessInfo.processInfo.thermalState),
            @"fixture": @{
                @"capture": contract[@"capture"],
                @"reference_index": contract[@"reference_index"],
                @"width": @(params.width),
                @"height": @(params.height),
                @"depth_samples": @(params.depthCount),
                @"source_count": @(params.sourceCount),
                @"patch_n": @(params.patchN),
                @"min_views": @(params.minViews),
                @"learned_model_consumed": @NO,
                @"training_data_consumed": @NO,
                @"third_party_matcher_output_consumed": @NO,
                @"lidar_or_scene_depth_consumed": @NO,
            },
            @"streaming": @{
                @"input_gray_bytes": @(grayData.length),
                @"output_bytes": @(
                    bestIndexBuffer.length + bestScoreBuffer.length + secondScoreBuffer.length +
                    viewsBuffer.length + acceptedBuffer.length),
                @"peak_sampled_rss_bytes": @(peakRSS),
            },
            @"parity": @{
                @"expected_accepted_pixels": manifest[@"expected"][@"accepted_pixels"],
                @"actual_accepted_pixels": @(parity.actual_accepted_pixels),
                @"valid_mismatch_count": @(parity.valid_mismatch_count),
                @"accepted_best_index_mismatch_count": @(
                    parity.accepted_best_index_mismatch_count),
                @"all_valid_best_index_mismatch_count": @(
                    parity.all_valid_best_index_mismatch_count),
                @"views_mismatch_count": @(parity.views_mismatch_count),
                @"accepted_mismatch_count": @(parity.accepted_mismatch_count),
                @"compared_score_pixels": @(parity.compared_score_pixels),
                @"best_score_mean_abs": @(parity.best_score_mean_abs),
                @"best_score_max_abs": @(parity.best_score_max_abs),
                @"second_score_mean_abs": @(parity.second_score_mean_abs),
                @"second_score_max_abs": @(parity.second_score_max_abs),
            },
            @"registered_thresholds": registeredThresholds,
            @"runs": runs,
        };
        NSData* reportData = [NSJSONSerialization dataWithJSONObject:report
            options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
        if (!reportData || ![reportData writeToURL:latestURL options:NSDataWritingAtomic error:&error]) {
            [self fail:[NSString stringWithFormat:@"result write failed: %@", error]];
            return;
        }
        NSDictionary* cold = runs.firstObject;
        NSDictionary* warm = runs.lastObject;
        [self setStatus:[NSString stringWithFormat:
            @"PW Detector-Free Bench %@\n\nA16 known-pose sweep: %@\naccepted %lu/%@ · mismatch %lu\nbest index/view mismatch %lu/%lu\nscore mean/max %.4g/%.4g\ncold/warm GPU %.1f/%.1f ms\npeak RSS %.1f MB · thermal %@\n\n%@",
            parityPass ? @"COMPLETE" : @"FAILED",
            parityPass ? @"EXACT" : @"MISMATCH",
            (unsigned long)parity.actual_accepted_pixels, manifest[@"expected"][@"accepted_pixels"],
            (unsigned long)parity.accepted_mismatch_count,
            (unsigned long)parity.accepted_best_index_mismatch_count,
            (unsigned long)parity.views_mismatch_count,
            parity.best_score_mean_abs, parity.best_score_max_abs,
            [cold[@"gpu_seconds"] doubleValue] * 1000.0,
            [warm[@"gpu_seconds"] doubleValue] * 1000.0,
            peakRSS / 1048576.0,
            report[@"thermal_final"], latestURL.path]];
    }
}

@end
