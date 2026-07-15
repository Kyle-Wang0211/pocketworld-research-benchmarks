#import "AppDelegate.h"

#import <CommonCrypto/CommonDigest.h>
#import <Metal/Metal.h>
#import <MetalKit/MetalKit.h>
#import <mach/mach.h>
#import <simd/simd.h>
#import <sys/sysctl.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <functional>
#include <limits>
#include <numeric>
#include <optional>
#include <string>
#include <vector>

namespace {

constexpr NSUInteger kRunCount = 3;

struct MetalParams {
    std::uint32_t pointCount;
    std::uint32_t patchN;
    std::uint32_t width;
    std::uint32_t height;
    float patchRadius;
    float minStdU8;
    float padding0;
    float padding1;
    simd_float4 basisU;
    simd_float4 basisV;
    simd_float4 projection0;
    simd_float4 projection1;
    simd_float4 projection2;
};

struct Score {
    int views = 0;
    double ncc = 0.0;
    double parallax = 0.0;
};

struct CliqueResult {
    std::vector<int> members;
    double median = -std::numeric_limits<double>::infinity();
};

NSString* const kShaderSource = @R"METAL(
#include <metal_stdlib>
using namespace metal;

struct Params {
    uint point_count;
    uint patch_n;
    uint width;
    uint height;
    float patch_radius;
    float min_std_u8;
    float padding0;
    float padding1;
    float4 basis_u;
    float4 basis_v;
    float4 projection0;
    float4 projection1;
    float4 projection2;
};

kernel void normalize_plane_patches(
    texture2d<float, access::read> image [[texture(0)]],
    device const float4* points [[buffer(0)]],
    constant Params& params [[buffer(1)]],
    device float* normalized [[buffer(2)]],
    device uint* valid [[buffer(3)]],
    device float* stddev_u8 [[buffer(4)]],
    uint gid [[thread_position_in_grid]]) {
    if (gid >= params.point_count) return;
    constexpr uint max_samples = 81;
    float gray[max_samples];
    const uint sample_count = params.patch_n * params.patch_n;
    bool inside = sample_count <= max_samples;
    float sum = 0.0f;
    const float4 center = points[gid];
    for (uint y_index = 0; y_index < params.patch_n && inside; ++y_index) {
        const float v = params.patch_n == 1 ? 0.0f :
            (-params.patch_radius + 2.0f * params.patch_radius *
             float(y_index) / float(params.patch_n - 1));
        for (uint x_index = 0; x_index < params.patch_n; ++x_index) {
            const float u = params.patch_n == 1 ? 0.0f :
                (-params.patch_radius + 2.0f * params.patch_radius *
                 float(x_index) / float(params.patch_n - 1));
            const uint sample_index = x_index * params.patch_n + y_index;
            const float4 world = float4(
                center.xyz + params.basis_u.xyz * u + params.basis_v.xyz * v, 1.0f);
            const float z = dot(params.projection2, world);
            if (z <= 0.05f) { inside = false; break; }
            const float x = dot(params.projection0, world) / z;
            const float y = dot(params.projection1, world) / z;
            if (x < 0.0f || y < 0.0f || x > float(params.width - 1) ||
                y > float(params.height - 1)) { inside = false; break; }
            const uint x0 = uint(floor(x));
            const uint y0 = uint(floor(y));
            const uint x1 = min(x0 + 1, params.width - 1);
            const uint y1 = min(y0 + 1, params.height - 1);
            const float wx = x - float(x0);
            const float wy = y - float(y0);
            const float3 top = mix(image.read(uint2(x0, y0)).rgb,
                                   image.read(uint2(x1, y0)).rgb, wx);
            const float3 bottom = mix(image.read(uint2(x0, y1)).rgb,
                                      image.read(uint2(x1, y1)).rgb, wx);
            const float3 rgb = mix(top, bottom, wy);
            const float value = dot(rgb, float3(0.299f, 0.587f, 0.114f));
            gray[sample_index] = value;
            sum += value;
        }
    }
    const uint output_base = gid * sample_count;
    if (!inside) {
        valid[gid] = 0;
        stddev_u8[gid] = 0.0f;
        for (uint index = 0; index < sample_count; ++index) normalized[output_base + index] = 0.0f;
        return;
    }
    const float mean = sum / float(sample_count);
    float sum_squared = 0.0f;
    for (uint index = 0; index < sample_count; ++index) {
        const float centered = gray[index] - mean;
        sum_squared += centered * centered;
    }
    const float sigma_u8 = sqrt(sum_squared / float(sample_count)) * 255.0f;
    stddev_u8[gid] = sigma_u8;
    if (sigma_u8 < params.min_std_u8) {
        valid[gid] = 0;
        for (uint index = 0; index < sample_count; ++index) normalized[output_base + index] = 0.0f;
        return;
    }
    valid[gid] = 1;
    const float denominator = sqrt(sum_squared) + 1.0e-9f;
    for (uint index = 0; index < sample_count; ++index) {
        normalized[output_base + index] = (gray[index] - mean) / denominator;
    }
}
)METAL";

NSString* hexDigest(const unsigned char* digest) {
    NSMutableString* value = [NSMutableString stringWithCapacity:CC_SHA256_DIGEST_LENGTH * 2];
    for (NSUInteger index = 0; index < CC_SHA256_DIGEST_LENGTH; ++index) {
        [value appendFormat:@"%02x", digest[index]];
    }
    return value;
}

NSString* sha256(NSData* data) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(data.bytes, static_cast<CC_LONG>(data.length), digest);
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

NSString* machineIdentifier() {
    size_t size = 0;
    sysctlbyname("hw.machine", nullptr, &size, nullptr, 0);
    std::string value(size, '\0');
    sysctlbyname("hw.machine", value.data(), &size, nullptr, 0);
    if (!value.empty() && value.back() == '\0') value.pop_back();
    return [NSString stringWithUTF8String:value.c_str()];
}

simd_float4 float4FromArray(NSArray* values, float w = 0.0f) {
    return simd_make_float4(
        [values[0] floatValue], [values[1] floatValue], [values[2] floatValue], w);
}

double median(std::vector<double> values) {
    if (values.empty()) return 0.0;
    std::sort(values.begin(), values.end());
    const size_t middle = values.size() / 2;
    return values.size() % 2 ? values[middle] : (values[middle - 1] + values[middle]) * 0.5;
}

CliqueResult largestConsistentClique(
    const std::vector<double>& ncc, int count, double threshold, int minimum) {
    CliqueResult best;
    if (count < minimum || count > 63) return best;
    std::vector<std::uint64_t> neighbors(static_cast<size_t>(count), 0);
    for (int row = 0; row < count; ++row) {
        for (int column = 0; column < count; ++column) {
            if (row != column && ncc[static_cast<size_t>(row * count + column)] >= threshold) {
                neighbors[static_cast<size_t>(row)] |= std::uint64_t{1} << column;
            }
        }
    }
    std::vector<int> current;
    auto consider = [&]() {
        if (current.size() < static_cast<size_t>(minimum) ||
            current.size() < best.members.size()) return;
        std::vector<double> pairs;
        for (size_t a = 0; a < current.size(); ++a) {
            for (size_t b = a + 1; b < current.size(); ++b) {
                pairs.push_back(ncc[static_cast<size_t>(current[a] * count + current[b])]);
            }
        }
        const double value = median(std::move(pairs));
        if (current.size() > best.members.size() || value > best.median) {
            best.members = current;
            best.median = value;
        }
    };
    std::function<void(std::uint64_t)> search = [&](std::uint64_t candidates) {
        const size_t required = std::max<size_t>(minimum, best.members.size());
        if (current.size() + static_cast<size_t>(__builtin_popcountll(candidates)) < required) return;
        if (candidates == 0) {
            consider();
            return;
        }
        std::uint64_t remaining = candidates;
        while (remaining) {
            const size_t loopRequired = std::max<size_t>(minimum, best.members.size());
            if (current.size() + static_cast<size_t>(__builtin_popcountll(remaining)) < loopRequired) break;
            const std::uint64_t lowest = remaining & (~remaining + 1);
            const int vertex = __builtin_ctzll(lowest);
            current.push_back(vertex);
            search(remaining & neighbors[static_cast<size_t>(vertex)]);
            current.pop_back();
            remaining &= ~lowest;
        }
    };
    search(count == 64 ? ~std::uint64_t{0} : ((std::uint64_t{1} << count) - 1));
    return best;
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
    self.statusView.text = @"PW Plane Sweep Bench\nloading cap50 floor owner/rescue fixture…";
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
    [self setStatus:[NSString stringWithFormat:@"PW Plane Sweep Bench FAILED\n\n%@", message]];
}

- (std::optional<Score>)scorePoint:(NSUInteger)pointIndex
                              point:(simd_float4)point
                             frames:(NSArray<NSDictionary*>*)frames
              candidateFrameIndices:(NSArray<NSNumber*>*)candidateFrameIndices
                            patches:(const float*)patches
                              valid:(const std::uint32_t*)valid
                         pointCount:(NSUInteger)pointCount
                        sampleCount:(NSUInteger)sampleCount
                       minimumViews:(int)minimumViews
                       nccThreshold:(double)nccThreshold
                  minimumParallax:(double)minimumParallax {
    std::vector<int> candidate;
    for (NSNumber* frameValue in candidateFrameIndices) {
        const NSUInteger frameIndex = frameValue.unsignedIntegerValue;
        if (frameIndex >= frames.count) continue;
        const size_t validIndex = frameIndex * pointCount + pointIndex;
        if (valid[validIndex]) {
            candidate.push_back(static_cast<int>(frameIndex));
        }
    }
    if (candidate.size() < static_cast<size_t>(minimumViews) || candidate.size() > 63) {
        return std::nullopt;
    }
    const int count = static_cast<int>(candidate.size());
    std::vector<double> ncc(static_cast<size_t>(count * count), 1.0);
    for (int a = 0; a < count; ++a) {
        const size_t aBase = (static_cast<size_t>(candidate[a]) * pointCount + pointIndex) * sampleCount;
        for (int b = a + 1; b < count; ++b) {
            const size_t bBase = (static_cast<size_t>(candidate[b]) * pointCount + pointIndex) * sampleCount;
            double dot = 0.0;
            for (NSUInteger sample = 0; sample < sampleCount; ++sample) {
                dot += static_cast<double>(patches[aBase + sample]) * patches[bBase + sample];
            }
            ncc[static_cast<size_t>(a * count + b)] = dot;
            ncc[static_cast<size_t>(b * count + a)] = dot;
        }
    }
    const CliqueResult best = largestConsistentClique(
        ncc, count, nccThreshold, minimumViews);
    if (best.members.size() < static_cast<size_t>(minimumViews)) return std::nullopt;
    double maxParallax = 0.0;
    for (size_t a = 0; a < best.members.size(); ++a) {
        const int frameA = candidate[best.members[a]];
        simd_float3 rayA = simd_normalize(point.xyz - float4FromArray(frames[frameA][@"camera_center_f32"]).xyz);
        for (size_t b = a + 1; b < best.members.size(); ++b) {
            const int frameB = candidate[best.members[b]];
            simd_float3 rayB = simd_normalize(point.xyz - float4FromArray(frames[frameB][@"camera_center_f32"]).xyz);
            const double cosine = std::clamp(static_cast<double>(simd_dot(rayA, rayB)), -1.0, 1.0);
            maxParallax = std::max(maxParallax, std::acos(cosine) * 180.0 / M_PI);
        }
    }
    if (maxParallax < minimumParallax) return std::nullopt;
    return Score{static_cast<int>(best.members.size()), best.median, maxParallax};
}

- (void)runBenchmark {
    @autoreleasepool {
        NSBundle* bundle = NSBundle.mainBundle;
        NSURL* manifestURL = [bundle URLForResource:@"fixture_manifest" withExtension:@"json"];
        NSURL* pointsURL = [bundle URLForResource:@"points" withExtension:@"f32"];
        NSURL* expectedPatchesURL = [bundle URLForResource:@"expected_normalized_patches" withExtension:@"f32"];
        NSURL* expectedValidURL = [bundle URLForResource:@"expected_valid" withExtension:@"u8"];
        if (!manifestURL || !pointsURL || !expectedPatchesURL || !expectedValidURL) {
            [self fail:@"fixture resources missing"];
            return;
        }
        NSError* error = nil;
        NSData* manifestData = [NSData dataWithContentsOfURL:manifestURL options:0 error:&error];
        NSDictionary* manifest = manifestData ? [NSJSONSerialization JSONObjectWithData:manifestData options:0 error:&error] : nil;
        NSData* pointData = [NSData dataWithContentsOfURL:pointsURL options:NSDataReadingMappedIfSafe error:&error];
        NSData* expectedPatchData = [NSData dataWithContentsOfURL:expectedPatchesURL options:NSDataReadingMappedIfSafe error:&error];
        NSData* expectedValidData = [NSData dataWithContentsOfURL:expectedValidURL options:NSDataReadingMappedIfSafe error:&error];
        if (!manifest || !pointData || !expectedPatchData || !expectedValidData) {
            [self fail:[NSString stringWithFormat:@"fixture parse failed: %@", error]];
            return;
        }
        NSArray<NSDictionary*>* frames = manifest[@"frames"];
        const NSUInteger pointCount = [manifest[@"point_count"] unsignedIntegerValue];
        const NSUInteger sampleCount = [manifest[@"patch_sample_count"] unsignedIntegerValue];
        const NSUInteger candidateCount = [manifest[@"candidate_count"] unsignedIntegerValue];
        if (pointData.length != pointCount * 3 * sizeof(float) ||
            expectedPatchData.length != frames.count * pointCount * sampleCount * sizeof(float) ||
            expectedValidData.length != frames.count * pointCount) {
            [self fail:@"fixture byte count mismatch"];
            return;
        }
        std::vector<simd_float4> points(pointCount);
        const float* packedPoints = static_cast<const float*>(pointData.bytes);
        for (NSUInteger index = 0; index < pointCount; ++index) {
            points[index] = simd_make_float4(
                packedPoints[index * 3], packedPoints[index * 3 + 1], packedPoints[index * 3 + 2], 1.0f);
        }
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        id<MTLCommandQueue> queue = [device newCommandQueue];
        const auto compileStarted = std::chrono::steady_clock::now();
        id<MTLLibrary> library = [device newLibraryWithSource:kShaderSource options:nil error:&error];
        id<MTLFunction> function = [library newFunctionWithName:@"normalize_plane_patches"];
        id<MTLComputePipelineState> pipeline = function ? [device newComputePipelineStateWithFunction:function error:&error] : nil;
        const double compileSeconds = std::chrono::duration<double>(
            std::chrono::steady_clock::now() - compileStarted).count();
        if (!pipeline || !queue) {
            [self fail:[NSString stringWithFormat:@"Metal compile failed: %@", error]];
            return;
        }
        id<MTLBuffer> pointBuffer = [device newBufferWithBytes:points.data()
                                                        length:points.size() * sizeof(simd_float4)
                                                       options:MTLResourceStorageModeShared];
        const NSUInteger patchBytes = frames.count * pointCount * sampleCount * sizeof(float);
        const NSUInteger validBytes = frames.count * pointCount * sizeof(std::uint32_t);
        id<MTLBuffer> patchBuffer = [device newBufferWithLength:patchBytes options:MTLResourceStorageModeShared];
        id<MTLBuffer> validBuffer = [device newBufferWithLength:validBytes options:MTLResourceStorageModeShared];
        id<MTLBuffer> stddevBuffer = [device newBufferWithLength:frames.count * pointCount * sizeof(float)
                                                       options:MTLResourceStorageModeShared];
        std::vector<MetalParams> parameters(frames.count);
        NSMutableArray* runs = [NSMutableArray array];
        uint64_t peakRSS = residentBytes();
        for (NSUInteger runIndex = 0; runIndex < kRunCount; ++runIndex) {
            std::memset(patchBuffer.contents, 0, patchBytes);
            std::memset(validBuffer.contents, 0, validBytes);
            double decodeSeconds = 0.0;
            double gpuSeconds = 0.0;
            const auto runStarted = std::chrono::steady_clock::now();
            for (NSUInteger frameIndex = 0; frameIndex < frames.count; ++frameIndex) {
                @autoreleasepool {
                    NSDictionary* frame = frames[frameIndex];
                    NSString* resource = frame[@"resource"];
                    NSURL* imageURL = [bundle URLForResource:resource.stringByDeletingPathExtension
                                               withExtension:resource.pathExtension];
                    const auto decodeStarted = std::chrono::steady_clock::now();
                    MTKTextureLoader* loader = [[MTKTextureLoader alloc] initWithDevice:device];
                    id<MTLTexture> texture = [loader newTextureWithContentsOfURL:imageURL options:@{
                        MTKTextureLoaderOptionSRGB: @NO,
                        MTKTextureLoaderOptionTextureUsage: @(MTLTextureUsageShaderRead),
                        MTKTextureLoaderOptionAllocateMipmaps: @NO,
                    } error:&error];
                    decodeSeconds += std::chrono::duration<double>(
                        std::chrono::steady_clock::now() - decodeStarted).count();
                    if (!texture) {
                        [self fail:[NSString stringWithFormat:@"texture %@ failed: %@", resource, error]];
                        return;
                    }
                    NSArray* projection = frame[@"projection_row_major_f32"];
                    MetalParams params{};
                    params.pointCount = static_cast<std::uint32_t>(pointCount);
                    params.patchN = static_cast<std::uint32_t>([manifest[@"patch_n"] unsignedIntegerValue]);
                    params.width = static_cast<std::uint32_t>(texture.width);
                    params.height = static_cast<std::uint32_t>(texture.height);
                    params.patchRadius = [manifest[@"patch_radius_m"] floatValue];
                    params.minStdU8 = [manifest[@"min_std_u8"] floatValue];
                    params.basisU = float4FromArray(manifest[@"basis_u_f32"]);
                    params.basisV = float4FromArray(manifest[@"basis_v_f32"]);
                    params.projection0 = simd_make_float4([projection[0] floatValue], [projection[1] floatValue], [projection[2] floatValue], [projection[3] floatValue]);
                    params.projection1 = simd_make_float4([projection[4] floatValue], [projection[5] floatValue], [projection[6] floatValue], [projection[7] floatValue]);
                    params.projection2 = simd_make_float4([projection[8] floatValue], [projection[9] floatValue], [projection[10] floatValue], [projection[11] floatValue]);
                    parameters[frameIndex] = params;
                    id<MTLCommandBuffer> command = [queue commandBuffer];
                    id<MTLComputeCommandEncoder> encoder = [command computeCommandEncoder];
                    [encoder setComputePipelineState:pipeline];
                    [encoder setTexture:texture atIndex:0];
                    [encoder setBuffer:pointBuffer offset:0 atIndex:0];
                    [encoder setBytes:&params length:sizeof(params) atIndex:1];
                    [encoder setBuffer:patchBuffer offset:frameIndex * pointCount * sampleCount * sizeof(float) atIndex:2];
                    [encoder setBuffer:validBuffer offset:frameIndex * pointCount * sizeof(std::uint32_t) atIndex:3];
                    [encoder setBuffer:stddevBuffer offset:frameIndex * pointCount * sizeof(float) atIndex:4];
                    const NSUInteger width = std::min<NSUInteger>(pipeline.maxTotalThreadsPerThreadgroup, 64);
                    [encoder dispatchThreads:MTLSizeMake(pointCount, 1, 1)
                        threadsPerThreadgroup:MTLSizeMake(width, 1, 1)];
                    [encoder endEncoding];
                    const auto gpuStarted = std::chrono::steady_clock::now();
                    [command commit];
                    [command waitUntilCompleted];
                    gpuSeconds += std::chrono::duration<double>(
                        std::chrono::steady_clock::now() - gpuStarted).count();
                    if (command.status != MTLCommandBufferStatusCompleted) {
                        [self fail:[NSString stringWithFormat:@"GPU command failed: %@", command.error]];
                        return;
                    }
                    peakRSS = std::max(peakRSS, residentBytes());
                    [self setStatus:[NSString stringWithFormat:
                        @"PW Plane Sweep Bench\nrun %lu/%lu · frame %lu/%lu\nthermal: %@\nRSS: %.1f MB",
                        (unsigned long)(runIndex + 1), (unsigned long)kRunCount,
                        (unsigned long)(frameIndex + 1), (unsigned long)frames.count,
                        thermalStateName(NSProcessInfo.processInfo.thermalState),
                        residentBytes() / 1048576.0]];
                }
            }
            const double elapsed = std::chrono::duration<double>(
                std::chrono::steady_clock::now() - runStarted).count();
            [runs addObject:@{
                @"index": @(runIndex),
                @"kind": runIndex == 0 ? @"cold" : @"warm",
                @"elapsed_seconds": @(elapsed),
                @"decode_seconds": @(decodeSeconds),
                @"gpu_dispatch_and_wait_seconds": @(gpuSeconds),
                @"thermal_after": thermalStateName(NSProcessInfo.processInfo.thermalState),
                @"rss_after_bytes": @(residentBytes()),
            }];
        }

        const float* outputPatches = static_cast<const float*>(patchBuffer.contents);
        const std::uint32_t* outputValid = static_cast<const std::uint32_t*>(validBuffer.contents);
        const float* expectedPatches = static_cast<const float*>(expectedPatchData.bytes);
        const std::uint8_t* expectedValid = static_cast<const std::uint8_t*>(expectedValidData.bytes);
        NSUInteger validMismatch = 0;
        double absoluteSum = 0.0;
        double maxAbsolute = 0.0;
        NSUInteger compared = 0;
        for (NSUInteger frame = 0; frame < frames.count; ++frame) {
            for (NSUInteger point = 0; point < pointCount; ++point) {
                const size_t validIndex = frame * pointCount + point;
                if ((outputValid[validIndex] != 0) != (expectedValid[validIndex] != 0)) ++validMismatch;
                if (!expectedValid[validIndex] || !outputValid[validIndex]) continue;
                const size_t base = validIndex * sampleCount;
                for (NSUInteger sample = 0; sample < sampleCount; ++sample) {
                    const double difference = fabs(static_cast<double>(outputPatches[base + sample]) - expectedPatches[base + sample]);
                    absoluteSum += difference;
                    maxAbsolute = std::max(maxAbsolute, difference);
                    ++compared;
                }
            }
        }
        NSArray<NSArray<NSNumber*>*>* pointCandidates = manifest[@"candidate_resource_frame_indices"];
        const int minimumViews = [manifest[@"min_views"] intValue];
        const NSUInteger baseMaxViews = [manifest[@"base_max_views"] unsignedIntegerValue];
        const double nccThreshold = [manifest[@"ncc_min"] doubleValue];
        const double minimumParallax = [manifest[@"min_parallax_deg"] doubleValue];
        const double rescueMinimumNCC = [manifest[@"rescue_min_ncc"] doubleValue];
        const double rescueMinimumParallax = [manifest[@"rescue_min_parallax_deg"] doubleValue];
        const int rescueMinimumViews = [manifest[@"rescue_min_views"] intValue];
        if (pointCandidates.count != candidateCount || pointCount != candidateCount) {
            [self fail:@"fixture point candidate table mismatch"];
            return;
        }
        std::vector<int> accepted;
        std::vector<int> baseAccepted;
        std::vector<int> rescueAccepted;
        for (NSUInteger candidate = 0; candidate < candidateCount; ++candidate) {
            NSArray<NSNumber*>* allCandidateFrames = pointCandidates[candidate];
            const NSUInteger baseCount = std::min(baseMaxViews, allCandidateFrames.count);
            NSArray<NSNumber*>* baseCandidateFrames = [allCandidateFrames subarrayWithRange:NSMakeRange(0, baseCount)];
            auto score = [self scorePoint:candidate point:points[candidate] frames:frames
                    candidateFrameIndices:baseCandidateFrames patches:outputPatches valid:outputValid
                    pointCount:pointCount sampleCount:sampleCount minimumViews:minimumViews
                    nccThreshold:nccThreshold minimumParallax:minimumParallax];
            bool acceptedByRescue = false;
            if (!score && allCandidateFrames.count > baseCount) {
                auto rescue = [self scorePoint:candidate point:points[candidate] frames:frames
                        candidateFrameIndices:allCandidateFrames patches:outputPatches valid:outputValid
                        pointCount:pointCount sampleCount:sampleCount minimumViews:minimumViews
                        nccThreshold:nccThreshold minimumParallax:minimumParallax];
                if (rescue && rescue->views >= rescueMinimumViews &&
                    rescue->ncc >= rescueMinimumNCC &&
                    rescue->parallax >= rescueMinimumParallax) {
                    score = rescue;
                    acceptedByRescue = true;
                }
            }
            if (!score) continue;
            accepted.push_back(static_cast<int>(candidate));
            (acceptedByRescue ? rescueAccepted : baseAccepted).push_back(static_cast<int>(candidate));
        }
        NSArray<NSNumber*>* expectedAccepted = manifest[@"expected"][@"accepted_local_indices"];
        NSArray<NSNumber*>* expectedBaseAccepted = manifest[@"expected"][@"base_accepted_local_indices"];
        NSArray<NSNumber*>* expectedRescueAccepted = manifest[@"expected"][@"rescue_accepted_local_indices"];
        std::vector<int> expectedAcceptedVector;
        std::vector<int> expectedBaseAcceptedVector;
        std::vector<int> expectedRescueAcceptedVector;
        for (NSNumber* value in expectedAccepted) expectedAcceptedVector.push_back(value.intValue);
        for (NSNumber* value in expectedBaseAccepted) expectedBaseAcceptedVector.push_back(value.intValue);
        for (NSNumber* value in expectedRescueAccepted) expectedRescueAcceptedVector.push_back(value.intValue);
        const BOOL acceptedExact = accepted == expectedAcceptedVector;
        const BOOL baseAcceptedExact = baseAccepted == expectedBaseAcceptedVector;
        const BOOL rescueAcceptedExact = rescueAccepted == expectedRescueAcceptedVector;
        NSMutableArray* acceptedJSON = [NSMutableArray array];
        NSMutableArray* baseAcceptedJSON = [NSMutableArray array];
        NSMutableArray* rescueAcceptedJSON = [NSMutableArray array];
        for (int value : accepted) [acceptedJSON addObject:@(value)];
        for (int value : baseAccepted) [baseAcceptedJSON addObject:@(value)];
        for (int value : rescueAccepted) [rescueAcceptedJSON addObject:@(value)];
        const BOOL parityPass = acceptedExact && baseAcceptedExact && rescueAcceptedExact && validMismatch == 0 &&
            (compared == 0 || absoluteSum / compared < 2.0e-4) && maxAbsolute < 1.0e-2;

        NSArray<NSURL*>* documents = [[NSFileManager defaultManager]
            URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask];
        NSURL* directory = [documents.firstObject URLByAppendingPathComponent:@"planesweep_bench" isDirectory:YES];
        [[NSFileManager defaultManager] createDirectoryAtURL:directory withIntermediateDirectories:YES attributes:nil error:&error];
        NSURL* latestURL = [directory URLByAppendingPathComponent:@"latest.json"];
        NSDictionary* report = @{
            @"schema": @"pocketworld_a16_planesweep_streaming_bench_v2",
            @"status": parityPass ? @"complete" : @"failed",
            @"decision": parityPass ? @"PASS_A16_FLOOR_OWNER_RESCUE_PARITY" : @"FAIL_A16_FLOOR_OWNER_RESCUE_PARITY",
            @"device_model": machineIdentifier() ?: @"unknown",
            @"os_version": UIDevice.currentDevice.systemVersion,
            @"metal_device": device.name ?: @"unknown",
            @"thermal_final": thermalStateName(NSProcessInfo.processInfo.thermalState),
            @"manifest_sha256": sha256(manifestData),
            @"compile_seconds": @(compileSeconds),
            @"fixture": @{
                @"surface_id": manifest[@"surface_id"],
                @"candidate_count": @(candidateCount),
                @"hypothesis_count": manifest[@"hypothesis_count"],
                @"point_count": @(pointCount),
                @"frame_count": @(frames.count),
                @"patch_n": manifest[@"patch_n"],
                @"base_max_views": manifest[@"base_max_views"],
                @"max_views": manifest[@"max_views"],
                @"forbidden_matcher_outputs_consumed": @NO,
            },
            @"streaming": @{
                @"resident_4k_textures_at_once": @1,
                @"peak_sampled_rss_bytes": @(peakRSS),
                @"output_patch_buffer_bytes": @(patchBytes),
            },
            @"parity": @{
                @"expected_accepted": expectedAccepted,
                @"actual_accepted": acceptedJSON,
                @"accepted_exact": @(acceptedExact),
                @"expected_base_accepted": expectedBaseAccepted,
                @"actual_base_accepted": baseAcceptedJSON,
                @"base_accepted_exact": @(baseAcceptedExact),
                @"expected_rescue_accepted": expectedRescueAccepted,
                @"actual_rescue_accepted": rescueAcceptedJSON,
                @"rescue_accepted_exact": @(rescueAcceptedExact),
                @"valid_mismatch_count": @(validMismatch),
                @"normalized_patch_compared_values": @(compared),
                @"normalized_patch_mean_abs": @(compared ? absoluteSum / compared : 0.0),
                @"normalized_patch_max_abs": @(maxAbsolute),
            },
            @"runs": runs,
        };
        NSData* reportData = [NSJSONSerialization dataWithJSONObject:report
            options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
        if (!reportData || ![reportData writeToURL:latestURL options:NSDataWritingAtomic error:&error]) {
            [self fail:[NSString stringWithFormat:@"result write failed: %@", error]];
            return;
        }
        NSDictionary* first = runs.firstObject;
        NSDictionary* last = runs.lastObject;
        [self setStatus:[NSString stringWithFormat:
            @"PW Plane Sweep Bench %@\n\nA16 floor owner/rescue: %@\naccepted: %lu/%@ · base %lu · rescue %lu\nvalid mismatch: %lu\npatch mean/max: %.6g / %.6g\ncompile: %.1f ms\ncold: %.1f ms\nwarm: %.1f ms\npeak RSS: %.1f MB\nthermal: %@\n\n%@",
            parityPass ? @"COMPLETE" : @"FAILED",
            (acceptedExact && baseAcceptedExact && rescueAcceptedExact) ? @"EXACT" : @"MISMATCH",
            (unsigned long)accepted.size(), manifest[@"expected"][@"accepted_count"],
            (unsigned long)baseAccepted.size(), (unsigned long)rescueAccepted.size(),
            (unsigned long)validMismatch,
            compared ? absoluteSum / compared : 0.0, maxAbsolute,
            compileSeconds * 1000.0,
            [first[@"elapsed_seconds"] doubleValue] * 1000.0,
            [last[@"elapsed_seconds"] doubleValue] * 1000.0,
            peakRSS / 1048576.0,
            report[@"thermal_final"], latestURL.path]];
    }
}

@end
