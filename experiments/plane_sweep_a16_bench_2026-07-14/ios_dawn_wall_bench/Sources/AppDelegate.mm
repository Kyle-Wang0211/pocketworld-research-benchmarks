#import "AppDelegate.h"

#import <mach/mach.h>
#import <simd/simd.h>
#import <sys/sysctl.h>

#include <webgpu/webgpu_cpp.h>

#include "wall_scale_rescue_contract.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <optional>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace {

struct alignas(16) Params {
    std::uint32_t pointCount;
    std::uint32_t patchN;
    std::uint32_t width;
    std::uint32_t height;
    float patchRadius;
    float minStdU8;
    float padding0;
    float padding1;
    float basisU[4];
    float basisV[4];
    float projection0[4];
    float projection1[4];
    float projection2[4];
};
static_assert(sizeof(Params) == 112);

struct Score {
    int views = 0;
    double ncc = 0.0;
    double parallax = 0.0;
};

NSString* thermalStateName(NSProcessInfoThermalState state) {
    switch (state) {
        case NSProcessInfoThermalStateNominal: return @"nominal";
        case NSProcessInfoThermalStateFair: return @"fair";
        case NSProcessInfoThermalStateSerious: return @"serious";
        case NSProcessInfoThermalStateCritical: return @"critical";
    }
    return @"unknown";
}

std::uint64_t residentBytes() {
    mach_task_basic_info_data_t info{};
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    return task_info(mach_task_self(), MACH_TASK_BASIC_INFO,
                     reinterpret_cast<task_info_t>(&info), &count) == KERN_SUCCESS
        ? info.resident_size : 0;
}

NSString* machineIdentifier() {
    size_t size = 0;
    sysctlbyname("hw.machine", nullptr, &size, nullptr, 0);
    std::string value(size, '\0');
    sysctlbyname("hw.machine", value.data(), &size, nullptr, 0);
    if (!value.empty() && value.back() == '\0') value.pop_back();
    return [NSString stringWithUTF8String:value.c_str()];
}

NSData* resource(NSString* filename) {
    NSURL* url = [NSBundle.mainBundle URLForResource:filename.stringByDeletingPathExtension
                                       withExtension:filename.pathExtension];
    return url ? [NSData dataWithContentsOfURL:url options:NSDataReadingMappedIfSafe error:nil]
               : nil;
}

NSURL* resultDirectory() {
    NSURL* documents = [[NSFileManager defaultManager]
        URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    return [documents URLByAppendingPathComponent:@"wall_planesweep_dawn_bench" isDirectory:YES];
}

simd_float4 float4FromArray(NSArray<NSNumber*>* values, float w = 0.0f) {
    return simd_make_float4(values[0].floatValue, values[1].floatValue,
                            values[2].floatValue, values.count > 3 ? values[3].floatValue : w);
}

void copyFloat4(float destination[4], NSArray<NSNumber*>* source, float defaultW = 0.0f) {
    destination[0] = source[0].floatValue;
    destination[1] = source[1].floatValue;
    destination[2] = source[2].floatValue;
    destination[3] = source.count > 3 ? source[3].floatValue : defaultW;
}

std::vector<int> intVector(NSArray<NSNumber*>* values) {
    std::vector<int> output;
    output.reserve(values.count);
    for (NSNumber* value in values) output.push_back(value.intValue);
    return output;
}

NSArray<NSNumber*>* jsonVector(const std::vector<int>& values) {
    NSMutableArray<NSNumber*>* output = [NSMutableArray arrayWithCapacity:values.size()];
    for (int value : values) [output addObject:@(value)];
    return output;
}

bool mapCopy(wgpu::Instance& instance, wgpu::Buffer& buffer,
             std::size_t bytes, std::vector<std::uint8_t>& output) {
    bool success = false;
    auto future = buffer.MapAsync(
        wgpu::MapMode::Read, 0, bytes, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::MapAsyncStatus status, wgpu::StringView) {
            success = status == wgpu::MapAsyncStatus::Success;
        });
    if (instance.WaitAny(future, UINT64_MAX) != wgpu::WaitStatus::Success || !success) {
        return false;
    }
    const void* data = buffer.GetConstMappedRange(0, bytes);
    if (!data) return false;
    output.resize(bytes);
    std::memcpy(output.data(), data, bytes);
    buffer.Unmap();
    return true;
}

std::optional<Score> scorePoint(
    std::size_t scaleIndex,
    std::size_t pointIndex,
    NSArray<NSDictionary*>* frames,
    NSArray<NSNumber*>* candidateFrameIndices,
    const std::vector<simd_float4>& points,
    const float* patches,
    const std::uint32_t* valid,
    std::size_t frameCount,
    std::size_t pointCount,
    std::size_t sampleCount,
    int minimumViews,
    double nccThreshold,
    double minimumParallax) {
    std::vector<int> candidates;
    for (NSNumber* value in candidateFrameIndices) {
        const std::size_t frame = value.unsignedIntegerValue;
        if (frame >= frameCount) continue;
        const std::size_t validIndex = (scaleIndex * frameCount + frame) * pointCount + pointIndex;
        if (valid[validIndex]) candidates.push_back(static_cast<int>(frame));
    }
    if (candidates.size() < static_cast<std::size_t>(minimumViews) || candidates.size() > 63) {
        return std::nullopt;
    }
    const int count = static_cast<int>(candidates.size());
    std::vector<double> ncc(static_cast<std::size_t>(count * count), 1.0);
    for (int a = 0; a < count; ++a) {
        const std::size_t aBase =
            (((scaleIndex * frameCount + static_cast<std::size_t>(candidates[a])) * pointCount +
              pointIndex) * sampleCount);
        for (int b = a + 1; b < count; ++b) {
            const std::size_t bBase =
                (((scaleIndex * frameCount + static_cast<std::size_t>(candidates[b])) * pointCount +
                  pointIndex) * sampleCount);
            double dot = 0.0;
            for (std::size_t sample = 0; sample < sampleCount; ++sample) {
                dot += static_cast<double>(patches[aBase + sample]) * patches[bBase + sample];
            }
            ncc[static_cast<std::size_t>(a * count + b)] = dot;
            ncc[static_cast<std::size_t>(b * count + a)] = dot;
        }
    }
    const auto clique = pocketworld::wall_planesweep::largest_consistent_clique(
        ncc, count, nccThreshold, minimumViews);
    if (clique.members.size() < static_cast<std::size_t>(minimumViews)) {
        return std::nullopt;
    }
    double maxParallax = 0.0;
    for (std::size_t a = 0; a < clique.members.size(); ++a) {
        const int frameA = candidates[clique.members[a]];
        const simd_float3 cameraA = float4FromArray(frames[frameA][@"camera_center_f32"]).xyz;
        const simd_float3 rayA = simd_normalize(points[pointIndex].xyz - cameraA);
        for (std::size_t b = a + 1; b < clique.members.size(); ++b) {
            const int frameB = candidates[clique.members[b]];
            const simd_float3 cameraB = float4FromArray(frames[frameB][@"camera_center_f32"]).xyz;
            const simd_float3 rayB = simd_normalize(points[pointIndex].xyz - cameraB);
            const double cosine = std::clamp(static_cast<double>(simd_dot(rayA, rayB)), -1.0, 1.0);
            maxParallax = std::max(maxParallax, std::acos(cosine) * 180.0 / M_PI);
        }
    }
    if (maxParallax < minimumParallax) return std::nullopt;
    return Score{static_cast<int>(clique.members.size()), clique.median, maxParallax};
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
    self.statusView.text = @"PW wall plane-sweep Dawn bench\nloading strict two-scale fixture…";
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

- (void)setStatus:(NSString*)text {
    dispatch_async(dispatch_get_main_queue(), ^{ self.statusView.text = text; });
}

- (void)writeReport:(NSDictionary*)report {
    NSError* error = nil;
    NSURL* directory = resultDirectory();
    [[NSFileManager defaultManager] createDirectoryAtURL:directory
        withIntermediateDirectories:YES attributes:nil error:&error];
    NSData* json = [NSJSONSerialization dataWithJSONObject:report
        options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:&error];
    [json writeToURL:[directory URLByAppendingPathComponent:@"latest.json"]
             options:NSDataWritingAtomic error:&error];
}

- (void)fail:(NSString*)message {
    NSDictionary* report = @{
        @"schema": @"pocketworld_dawn_wall_scale_rescue_a16_bench_v1",
        @"status": @"failed",
        @"decision": @"FAIL_DAWN_A16_WALL_SCALE_RESCUE_RUNTIME",
        @"error": message ?: @"unknown",
        @"device_model": machineIdentifier() ?: @"unknown",
        @"thermal_final": thermalStateName(NSProcessInfo.processInfo.thermalState),
    };
    [self writeReport:report];
    [self setStatus:[NSString stringWithFormat:@"Wall Dawn bench FAILED\n\n%@", message]];
}

- (void)runBenchmark {
    @autoreleasepool {
        NSData* manifestData = resource(@"fixture_manifest.json");
        NSData* pointsData = resource(@"points.f32");
        NSData* expectedPatchesData = resource(@"expected_normalized_patches.f32");
        NSData* expectedValidData = resource(@"expected_valid.u8");
        NSURL* shaderURL = [NSBundle.mainBundle URLForResource:@"known_plane_patch_normalize"
                                                 withExtension:@"wgsl"];
        NSString* shaderString = shaderURL ? [NSString stringWithContentsOfURL:shaderURL
            encoding:NSUTF8StringEncoding error:nil] : nil;
        NSDictionary* manifest = manifestData ? [NSJSONSerialization JSONObjectWithData:manifestData
            options:0 error:nil] : nil;
        if (!manifest || !pointsData || !expectedPatchesData || !expectedValidData || !shaderString) {
            [self fail:@"fixture or shared WGSL resource missing"];
            return;
        }
        NSArray<NSDictionary*>* frames = manifest[@"frames"];
        NSArray<NSDictionary*>* scales = manifest[@"scales"];
        NSArray<NSArray<NSArray<NSNumber*>*>*>* candidateTables =
            manifest[@"candidate_resource_frame_indices_by_scale"];
        const std::size_t scaleCount = scales.count;
        const std::size_t frameCount = frames.count;
        const std::size_t pointCount = [manifest[@"point_count"] unsignedIntegerValue];
        const std::size_t candidateCount = [manifest[@"candidate_count"] unsignedIntegerValue];
        const std::size_t hypothesisCount = [manifest[@"hypothesis_count"] unsignedIntegerValue];
        const std::size_t sampleCount = [manifest[@"patch_sample_count"] unsignedIntegerValue];
        const std::size_t patchValueCount = scaleCount * frameCount * pointCount * sampleCount;
        const std::size_t validValueCount = scaleCount * frameCount * pointCount;
        if (scaleCount != 2 || pointCount != candidateCount * hypothesisCount ||
            pointsData.length != pointCount * 3 * sizeof(float) ||
            expectedPatchesData.length != patchValueCount * sizeof(float) ||
            expectedValidData.length != validValueCount || candidateTables.count != scaleCount) {
            [self fail:@"fixture byte count or shape mismatch"];
            return;
        }
        std::vector<simd_float4> points(pointCount);
        const float* packedPoints = static_cast<const float*>(pointsData.bytes);
        for (std::size_t index = 0; index < pointCount; ++index) {
            points[index] = simd_make_float4(
                packedPoints[index * 3], packedPoints[index * 3 + 1],
                packedPoints[index * 3 + 2], 1.0f);
        }

        static constexpr auto timedWait = wgpu::InstanceFeatureName::TimedWaitAny;
        wgpu::InstanceDescriptor instanceDescriptor{
            .requiredFeatureCount = 1, .requiredFeatures = &timedWait};
        wgpu::Instance instance = wgpu::CreateInstance(&instanceDescriptor);
        if (!instance) { [self fail:@"CreateInstance failed"]; return; }
        wgpu::Adapter adapter;
        wgpu::RequestAdapterOptions adapterOptions{};
        instance.WaitAny(instance.RequestAdapter(
            &adapterOptions, wgpu::CallbackMode::WaitAnyOnly,
            [&](wgpu::RequestAdapterStatus status, wgpu::Adapter value, wgpu::StringView) {
                if (status == wgpu::RequestAdapterStatus::Success) adapter = std::move(value);
            }), UINT64_MAX);
        if (!adapter) { [self fail:@"RequestAdapter failed"]; return; }
        wgpu::AdapterInfo adapterInfo{};
        adapter.GetInfo(&adapterInfo);
        std::string adapterName = adapterInfo.device.data
            ? std::string(adapterInfo.device.data,
                adapterInfo.device.length == WGPU_STRLEN
                    ? std::strlen(adapterInfo.device.data) : adapterInfo.device.length)
            : "unknown";
        wgpu::Device device;
        wgpu::DeviceDescriptor deviceDescriptor{};
        instance.WaitAny(adapter.RequestDevice(
            &deviceDescriptor, wgpu::CallbackMode::WaitAnyOnly,
            [&](wgpu::RequestDeviceStatus status, wgpu::Device value, wgpu::StringView) {
                if (status == wgpu::RequestDeviceStatus::Success) device = std::move(value);
            }), UINT64_MAX);
        if (!device) { [self fail:@"RequestDevice failed"]; return; }
        wgpu::Queue queue = device.GetQueue();

        auto makeInput = [&](const void* bytes, std::size_t length, wgpu::BufferUsage usage) {
            wgpu::BufferDescriptor descriptor{.usage = usage | wgpu::BufferUsage::CopyDst,
                                               .size = length};
            wgpu::Buffer buffer = device.CreateBuffer(&descriptor);
            queue.WriteBuffer(buffer, 0, bytes, length);
            return buffer;
        };
        auto makeOutput = [&](std::size_t bytes) {
            wgpu::BufferDescriptor descriptor{
                .usage = wgpu::BufferUsage::Storage | wgpu::BufferUsage::CopySrc,
                .size = bytes};
            return device.CreateBuffer(&descriptor);
        };
        auto makeStaging = [&](std::size_t bytes) {
            wgpu::BufferDescriptor descriptor{
                .usage = wgpu::BufferUsage::MapRead | wgpu::BufferUsage::CopyDst,
                .size = bytes};
            return device.CreateBuffer(&descriptor);
        };
        wgpu::Buffer pointBuffer = makeInput(
            points.data(), points.size() * sizeof(simd_float4), wgpu::BufferUsage::Storage);
        const std::size_t patchBytes = patchValueCount * sizeof(float);
        const std::size_t validBytes = validValueCount * sizeof(std::uint32_t);
        const std::size_t patchSliceBytes = pointCount * sampleCount * sizeof(float);
        const std::size_t validSliceBytes = pointCount * sizeof(std::uint32_t);
        wgpu::Buffer patchOutput = makeOutput(patchBytes);
        wgpu::Buffer validOutput = makeOutput(validBytes);
        wgpu::Buffer stddevOutput = makeOutput(validBytes);

        std::string wgsl(shaderString.UTF8String);
        wgpu::ShaderSourceWGSL shaderSource{};
        shaderSource.code = wgsl.c_str();
        wgpu::ShaderModuleDescriptor shaderDescriptor{};
        shaderDescriptor.nextInChain = &shaderSource;
        const auto compileStart = std::chrono::steady_clock::now();
        wgpu::ShaderModule shader = device.CreateShaderModule(&shaderDescriptor);
        wgpu::ComputePipelineDescriptor pipelineDescriptor{};
        pipelineDescriptor.compute.module = shader;
        pipelineDescriptor.compute.entryPoint = "main";
        wgpu::ComputePipeline pipeline = device.CreateComputePipeline(&pipelineDescriptor);
        const double compileMs = std::chrono::duration<double, std::milli>(
            std::chrono::steady_clock::now() - compileStart).count();
        if (!pipeline) { [self fail:@"WGSL pipeline compile failed"]; return; }

        std::uint64_t peakRSS = residentBytes();
        std::size_t largestFrameBytes = 0;
        auto waitQueue = [&]() {
            wgpu::QueueWorkDoneStatus status = wgpu::QueueWorkDoneStatus::Error;
            auto future = queue.OnSubmittedWorkDone(
                wgpu::CallbackMode::WaitAnyOnly,
                [&](wgpu::QueueWorkDoneStatus value, wgpu::StringView) { status = value; });
            return instance.WaitAny(future, UINT64_MAX) == wgpu::WaitStatus::Success &&
                   status == wgpu::QueueWorkDoneStatus::Success;
        };
        auto runOnce = [&]() -> double {
            const auto started = std::chrono::steady_clock::now();
            for (std::size_t scale = 0; scale < scaleCount; ++scale) {
                NSDictionary* scaleConfig = scales[scale];
                for (std::size_t frameIndex = 0; frameIndex < frameCount; ++frameIndex) {
                    @autoreleasepool {
                        NSDictionary* frame = frames[frameIndex];
                        NSData* pixels = resource(frame[@"resource"]);
                        const std::size_t expectedBytes =
                            [frame[@"width"] unsignedIntegerValue] *
                            [frame[@"height"] unsignedIntegerValue] * sizeof(std::uint32_t);
                        if (!pixels || pixels.length != expectedBytes) return -1.0;
                        largestFrameBytes = std::max(largestFrameBytes, expectedBytes);
                        wgpu::Buffer imageBuffer = makeInput(
                            pixels.bytes, pixels.length, wgpu::BufferUsage::Storage);
                        Params params{};
                        params.pointCount = static_cast<std::uint32_t>(pointCount);
                        params.patchN = [manifest[@"patch_n"] unsignedIntValue];
                        params.width = [frame[@"width"] unsignedIntValue];
                        params.height = [frame[@"height"] unsignedIntValue];
                        params.patchRadius = [scaleConfig[@"patch_radius_m"] floatValue];
                        params.minStdU8 = [scaleConfig[@"min_std_u8"] floatValue];
                        copyFloat4(params.basisU, manifest[@"basis_u_f32"]);
                        copyFloat4(params.basisV, manifest[@"basis_v_f32"]);
                        NSArray<NSNumber*>* projection = frame[@"projection_row_major_f32"];
                        copyFloat4(params.projection0, [projection subarrayWithRange:NSMakeRange(0, 4)]);
                        copyFloat4(params.projection1, [projection subarrayWithRange:NSMakeRange(4, 4)]);
                        copyFloat4(params.projection2, [projection subarrayWithRange:NSMakeRange(8, 4)]);
                        wgpu::Buffer paramsBuffer = makeInput(
                            &params, sizeof(params), wgpu::BufferUsage::Uniform);
                        const std::size_t combo = scale * frameCount + frameIndex;
                        wgpu::BindGroupEntry entries[6] = {
                            {.binding=0, .buffer=imageBuffer, .offset=0, .size=pixels.length},
                            {.binding=1, .buffer=pointBuffer, .offset=0,
                             .size=points.size() * sizeof(simd_float4)},
                            {.binding=2, .buffer=paramsBuffer, .offset=0, .size=sizeof(params)},
                            {.binding=3, .buffer=patchOutput, .offset=combo * patchSliceBytes,
                             .size=patchSliceBytes},
                            {.binding=4, .buffer=validOutput, .offset=combo * validSliceBytes,
                             .size=validSliceBytes},
                            {.binding=5, .buffer=stddevOutput, .offset=combo * validSliceBytes,
                             .size=validSliceBytes},
                        };
                        wgpu::BindGroupDescriptor bindDescriptor{
                            .layout = pipeline.GetBindGroupLayout(0),
                            .entryCount = 6, .entries = entries};
                        wgpu::BindGroup bindGroup = device.CreateBindGroup(&bindDescriptor);
                        wgpu::CommandEncoder encoder = device.CreateCommandEncoder();
                        wgpu::ComputePassEncoder pass = encoder.BeginComputePass();
                        pass.SetPipeline(pipeline);
                        pass.SetBindGroup(0, bindGroup);
                        pass.DispatchWorkgroups(static_cast<std::uint32_t>((pointCount + 63) / 64));
                        pass.End();
                        wgpu::CommandBuffer command = encoder.Finish();
                        queue.Submit(1, &command);
                        if (!waitQueue()) return -1.0;
                        peakRSS = std::max(peakRSS, residentBytes());
                    }
                }
            }
            return std::chrono::duration<double, std::milli>(
                std::chrono::steady_clock::now() - started).count();
        };

        const double warmupMs = runOnce();
        if (warmupMs < 0.0) { [self fail:@"Dawn streaming dispatch failed"]; return; }
        NSMutableArray* runs = [NSMutableArray array];
        double bestMs = std::numeric_limits<double>::infinity();
        for (int index = 0; index < 3; ++index) {
            const double elapsedMs = runOnce();
            if (elapsedMs < 0.0) { [self fail:@"Dawn measured dispatch failed"]; return; }
            bestMs = std::min(bestMs, elapsedMs);
            [runs addObject:@{
                @"index": @(index), @"wall_ms": @(elapsedMs),
                @"thermal_after": thermalStateName(NSProcessInfo.processInfo.thermalState),
                @"rss_after_bytes": @(residentBytes()),
            }];
        }

        auto readOutput = [&](wgpu::Buffer& source, std::size_t bytes,
                              std::vector<std::uint8_t>& output) {
            wgpu::Buffer staging = makeStaging(bytes);
            wgpu::CommandEncoder encoder = device.CreateCommandEncoder();
            encoder.CopyBufferToBuffer(source, 0, staging, 0, bytes);
            wgpu::CommandBuffer command = encoder.Finish();
            queue.Submit(1, &command);
            return mapCopy(instance, staging, bytes, output);
        };
        std::vector<std::uint8_t> rawPatches, rawValid, rawStddev;
        if (!readOutput(patchOutput, patchBytes, rawPatches) ||
            !readOutput(validOutput, validBytes, rawValid) ||
            !readOutput(stddevOutput, validBytes, rawStddev)) {
            [self fail:@"Dawn result readback failed"];
            return;
        }
        const float* patches = reinterpret_cast<const float*>(rawPatches.data());
        const std::uint32_t* valid = reinterpret_cast<const std::uint32_t*>(rawValid.data());
        const float* expectedPatches = static_cast<const float*>(expectedPatchesData.bytes);
        const std::uint8_t* expectedValid = static_cast<const std::uint8_t*>(expectedValidData.bytes);
        std::size_t validMismatch = 0;
        std::size_t compared = 0;
        double absoluteSum = 0.0;
        double maxAbsolute = 0.0;
        for (std::size_t index = 0; index < validValueCount; ++index) {
            if ((valid[index] != 0) != (expectedValid[index] != 0)) ++validMismatch;
            if (!valid[index] || !expectedValid[index]) continue;
            const std::size_t base = index * sampleCount;
            for (std::size_t sample = 0; sample < sampleCount; ++sample) {
                const double difference = std::abs(
                    static_cast<double>(patches[base + sample]) - expectedPatches[base + sample]);
                absoluteSum += difference;
                maxAbsolute = std::max(maxAbsolute, difference);
                ++compared;
            }
        }

        std::vector<int> acceptedByScale[2];
        for (std::size_t scale = 0; scale < scaleCount; ++scale) {
            NSDictionary* config = scales[scale];
            NSArray<NSArray<NSNumber*>*>* table = candidateTables[scale];
            const int minimumViews = [config[@"min_views"] intValue];
            const double nccThreshold = [config[@"ncc_min"] doubleValue];
            const double minimumParallax = [config[@"min_parallax_deg"] doubleValue];
            const double requiredMargin = [config[@"depth_ncc_margin"] doubleValue];
            NSNumber* postMinimum = config[@"post_min_ncc"];
            for (std::size_t candidate = 0; candidate < candidateCount; ++candidate) {
                const std::size_t centerIndex = candidate * hypothesisCount;
                auto center = scorePoint(
                    scale, centerIndex, frames, table[centerIndex], points, patches, valid,
                    frameCount, pointCount, sampleCount, minimumViews,
                    nccThreshold, minimumParallax);
                if (!center || (postMinimum && center->ncc < postMinimum.doubleValue)) continue;
                std::vector<std::pair<int, double>> alternatives;
                for (std::size_t hypothesis = 1; hypothesis < hypothesisCount; ++hypothesis) {
                    const std::size_t pointIndex = centerIndex + hypothesis;
                    auto alternative = scorePoint(
                        scale, pointIndex, frames, table[pointIndex], points, patches, valid,
                        frameCount, pointCount, sampleCount, minimumViews,
                        nccThreshold, minimumParallax);
                    if (alternative) alternatives.emplace_back(alternative->views, alternative->ncc);
                }
                const auto [unique, observedMargin] =
                    pocketworld::wall_planesweep::unique_depth_winner(
                        center->views, center->ncc, alternatives, requiredMargin);
                (void)observedMargin;
                if (unique) acceptedByScale[scale].push_back(static_cast<int>(candidate));
            }
        }
        std::set<int> unionSet(acceptedByScale[0].begin(), acceptedByScale[0].end());
        unionSet.insert(acceptedByScale[1].begin(), acceptedByScale[1].end());
        std::vector<int> unionAccepted(unionSet.begin(), unionSet.end());
        NSDictionary* expected = manifest[@"expected"];
        const std::vector<int> expectedBaseline =
            intVector(expected[@"baseline_accepted_local_indices"]);
        const std::vector<int> expectedRescue =
            intVector(expected[@"rescue_accepted_local_indices"]);
        const std::vector<int> expectedUnion =
            intVector(expected[@"union_accepted_local_indices"]);
        const bool baselineExact = acceptedByScale[0] == expectedBaseline;
        const bool rescueExact = acceptedByScale[1] == expectedRescue;
        const bool unionExact = unionAccepted == expectedUnion;
        const double meanAbsolute = compared ? absoluteSum / compared : 0.0;
        const bool patchParity = validMismatch == 0 && meanAbsolute < 2.0e-4 && maxAbsolute < 1.0e-2;
        const bool parityPass = patchParity && baselineExact && rescueExact && unionExact;

        NSDictionary* report = @{
            @"schema": @"pocketworld_dawn_wall_scale_rescue_a16_bench_v1",
            @"status": parityPass ? @"complete" : @"failed",
            @"decision": parityPass
                ? @"PASS_DAWN_A16_WALL_SCALE_RESCUE_PARITY"
                : @"FAIL_DAWN_A16_WALL_SCALE_RESCUE_PARITY",
            @"device_model": machineIdentifier() ?: @"unknown",
            @"os_version": UIDevice.currentDevice.systemVersion,
            @"adapter": [NSString stringWithUTF8String:adapterName.c_str()],
            @"backend_contract": @"shared WGSL through Dawn; Metal on Apple, Vulkan on Android/HarmonyOS",
            @"fixture_manifest": manifest,
            @"compile_ms": @(compileMs),
            @"warmup_ms": @(warmupMs),
            @"best_of_3_wall_ms": @(bestMs),
            @"runs": runs,
            @"streaming": @{
                @"resident_cropped_frames_at_once": @1,
                @"largest_cropped_frame_bytes": @(largestFrameBytes),
                @"output_patch_buffer_bytes": @(patchBytes),
                @"peak_sampled_rss_bytes": @(peakRSS),
            },
            @"parity": @{
                @"expected_baseline": expected[@"baseline_accepted_local_indices"],
                @"actual_baseline": jsonVector(acceptedByScale[0]),
                @"baseline_exact": @(baselineExact),
                @"expected_rescue": expected[@"rescue_accepted_local_indices"],
                @"actual_rescue": jsonVector(acceptedByScale[1]),
                @"rescue_exact": @(rescueExact),
                @"expected_union": expected[@"union_accepted_local_indices"],
                @"actual_union": jsonVector(unionAccepted),
                @"union_exact": @(unionExact),
                @"valid_mismatch_count": @(validMismatch),
                @"normalized_patch_compared_values": @(compared),
                @"normalized_patch_mean_abs": @(meanAbsolute),
                @"normalized_patch_max_abs": @(maxAbsolute),
            },
            @"thermal_final": thermalStateName(NSProcessInfo.processInfo.thermalState),
            @"learned_model_consumed": @NO,
            @"third_party_matcher_output_consumed": @NO,
            @"lidar_or_scene_depth_consumed": @NO,
        };
        [self writeReport:report];
        [self setStatus:[NSString stringWithFormat:
            @"Wall Dawn A16 %@\n\nbaseline %@ · rescue %@ · union %@\naccepted %lu + %lu => %lu\nvalid mismatch %lu\npatch mean/max %.6g / %.6g\nbest %.1f ms · RSS %.1f MB\nthermal %@",
            parityPass ? @"PASS" : @"FAIL",
            baselineExact ? @"EXACT" : @"MISMATCH",
            rescueExact ? @"EXACT" : @"MISMATCH",
            unionExact ? @"EXACT" : @"MISMATCH",
            (unsigned long)acceptedByScale[0].size(),
            (unsigned long)acceptedByScale[1].size(),
            (unsigned long)unionAccepted.size(),
            (unsigned long)validMismatch,
            meanAbsolute, maxAbsolute, bestMs, peakRSS / 1048576.0,
            thermalStateName(NSProcessInfo.processInfo.thermalState)]];
    }
}

@end
