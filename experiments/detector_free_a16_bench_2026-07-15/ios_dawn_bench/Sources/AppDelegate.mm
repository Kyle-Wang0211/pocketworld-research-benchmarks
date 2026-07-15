#import "AppDelegate.h"

#import <mach/mach.h>
#import <sys/sysctl.h>

#include <webgpu/webgpu_cpp.h>

#include "portable_depth_contract.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace {

struct alignas(16) Params {
    std::uint32_t width;
    std::uint32_t height;
    std::uint32_t pixel_count;
    std::uint32_t depth_count;
    std::uint32_t source_count;
    std::uint32_t patch_n;
    std::uint32_t min_views;
    std::uint32_t exclusion_radius;
    float min_std_u8;
    float ncc_min;
    float depth_margin;
    float inverse_depth_first;
    float inverse_depth_step;
    float padding0;
    float padding1;
    float padding2;
    float inverse_k[12];
};
static_assert(sizeof(Params) == 112);

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
    return url ? [NSData dataWithContentsOfURL:url] : nil;
}

NSURL* resultDirectory() {
    NSURL* documents = [[NSFileManager defaultManager]
        URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    return [documents URLByAppendingPathComponent:@"detector_free_dawn_bench" isDirectory:YES];
}

bool mapCopy(wgpu::Instance& instance, wgpu::Buffer& buffer,
             std::size_t bytes, std::vector<std::uint8_t>& output) {
    bool mapped = false;
    bool success = false;
    auto future = buffer.MapAsync(
        wgpu::MapMode::Read, 0, bytes, wgpu::CallbackMode::WaitAnyOnly,
        [&](wgpu::MapAsyncStatus status, wgpu::StringView) {
            success = status == wgpu::MapAsyncStatus::Success;
            mapped = true;
        });
    instance.WaitAny(future, UINT64_MAX);
    if (!mapped || !success) return false;
    const void* data = buffer.GetConstMappedRange(0, bytes);
    if (!data) return false;
    output.resize(bytes);
    std::memcpy(output.data(), data, bytes);
    buffer.Unmap();
    return true;
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
    self.statusView.text = @"PW detector-free Dawn bench\nloading shared WGSL…";
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
        @"schema": @"pocketworld_model_free_depth_sweep_dawn_a16_bench_v1",
        @"status": @"failed",
        @"decision": @"FAIL_DAWN_A16_RUNTIME",
        @"error": message ?: @"unknown",
        @"device_model": machineIdentifier() ?: @"unknown",
        @"thermal_final": thermalStateName(NSProcessInfo.processInfo.thermalState),
    };
    [self writeReport:report];
    [self setStatus:[NSString stringWithFormat:@"Dawn bench FAILED\n\n%@", message]];
}

- (void)runBenchmark {
    @autoreleasepool {
        NSData* paramsData = resource(@"params.bin");
        NSData* grayData = resource(@"gray_frames.f32");
        NSData* projectionData = resource(@"source_projections.f32");
        NSData* expectedIndexData = resource(@"expected_best_index.u16");
        NSData* expectedBestData = resource(@"expected_best_score.f32");
        NSData* expectedSecondData = resource(@"expected_second_score.f32");
        NSData* expectedViewsData = resource(@"expected_views.u8");
        NSData* expectedAcceptedData = resource(@"expected_accepted.u8");
        NSData* manifestData = resource(@"fixture_manifest.json");
        NSURL* shaderURL = [NSBundle.mainBundle URLForResource:@"known_pose_depth_sweep"
                                                 withExtension:@"wgsl"];
        NSString* shaderString = shaderURL ? [NSString stringWithContentsOfURL:shaderURL
            encoding:NSUTF8StringEncoding error:nil] : nil;
        if (paramsData.length != sizeof(Params) || !grayData || !projectionData ||
            !expectedIndexData || !expectedBestData || !expectedSecondData ||
            !expectedViewsData || !expectedAcceptedData || !manifestData || !shaderString) {
            [self fail:@"fixture or WGSL resource missing"];
            return;
        }
        Params params{};
        std::memcpy(&params, paramsData.bytes, sizeof(params));
        const std::size_t pixels = params.pixel_count;

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

        auto makeInput = [&](NSData* data, wgpu::BufferUsage usage) {
            wgpu::BufferDescriptor descriptor{.usage = usage | wgpu::BufferUsage::CopyDst,
                                               .size = data.length};
            wgpu::Buffer buffer = device.CreateBuffer(&descriptor);
            queue.WriteBuffer(buffer, 0, data.bytes, data.length);
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
        wgpu::Buffer gray = makeInput(grayData, wgpu::BufferUsage::Storage);
        wgpu::Buffer projections = makeInput(projectionData, wgpu::BufferUsage::Storage);
        wgpu::Buffer uniforms = makeInput(paramsData, wgpu::BufferUsage::Uniform);
        const std::size_t u32Bytes = pixels * sizeof(std::uint32_t);
        const std::size_t f32Bytes = pixels * sizeof(float);
        wgpu::Buffer outIndex = makeOutput(u32Bytes);
        wgpu::Buffer outBest = makeOutput(f32Bytes);
        wgpu::Buffer outSecond = makeOutput(f32Bytes);
        wgpu::Buffer outViews = makeOutput(u32Bytes);
        wgpu::Buffer outAccepted = makeOutput(u32Bytes);
        wgpu::Buffer stageIndex = makeStaging(u32Bytes);
        wgpu::Buffer stageBest = makeStaging(f32Bytes);
        wgpu::Buffer stageSecond = makeStaging(f32Bytes);
        wgpu::Buffer stageViews = makeStaging(u32Bytes);
        wgpu::Buffer stageAccepted = makeStaging(u32Bytes);

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

        wgpu::BindGroupEntry entries[8] = {
            {.binding=0, .buffer=gray, .offset=0, .size=grayData.length},
            {.binding=1, .buffer=projections, .offset=0, .size=projectionData.length},
            {.binding=2, .buffer=uniforms, .offset=0, .size=sizeof(Params)},
            {.binding=3, .buffer=outIndex, .offset=0, .size=u32Bytes},
            {.binding=4, .buffer=outBest, .offset=0, .size=f32Bytes},
            {.binding=5, .buffer=outSecond, .offset=0, .size=f32Bytes},
            {.binding=6, .buffer=outViews, .offset=0, .size=u32Bytes},
            {.binding=7, .buffer=outAccepted, .offset=0, .size=u32Bytes},
        };
        wgpu::BindGroupDescriptor bindDescriptor{
            .layout = pipeline.GetBindGroupLayout(0),
            .entryCount = 8,
            .entries = entries};
        wgpu::BindGroup bindGroup = device.CreateBindGroup(&bindDescriptor);
        const std::uint32_t groups = (params.pixel_count + 63u) / 64u;

        auto runOnce = [&]() -> double {
            const auto start = std::chrono::steady_clock::now();
            wgpu::CommandEncoder encoder = device.CreateCommandEncoder();
            wgpu::ComputePassEncoder pass = encoder.BeginComputePass();
            pass.SetPipeline(pipeline);
            pass.SetBindGroup(0, bindGroup);
            pass.DispatchWorkgroups(groups);
            pass.End();
            encoder.CopyBufferToBuffer(outIndex, 0, stageIndex, 0, u32Bytes);
            encoder.CopyBufferToBuffer(outBest, 0, stageBest, 0, f32Bytes);
            encoder.CopyBufferToBuffer(outSecond, 0, stageSecond, 0, f32Bytes);
            encoder.CopyBufferToBuffer(outViews, 0, stageViews, 0, u32Bytes);
            encoder.CopyBufferToBuffer(outAccepted, 0, stageAccepted, 0, u32Bytes);
            wgpu::CommandBuffer command = encoder.Finish();
            queue.Submit(1, &command);
            std::vector<std::uint8_t> sync;
            if (!mapCopy(instance, stageAccepted, u32Bytes, sync)) return -1.0;
            return std::chrono::duration<double, std::milli>(
                std::chrono::steady_clock::now() - start).count();
        };
        const double warmupMs = runOnce();
        NSMutableArray* runs = [NSMutableArray array];
        double bestMs = 1e30;
        for (int index = 0; index < 3; ++index) {
            const double ms = runOnce();
            if (ms < 0.0) { [self fail:@"Dawn dispatch/map failed"]; return; }
            bestMs = std::min(bestMs, ms);
            [runs addObject:@{ @"index": @(index), @"wall_ms": @(ms) }];
        }
        std::vector<std::uint8_t> rawIndex, rawBest, rawSecond, rawViews, rawAccepted;
        if (!mapCopy(instance, stageIndex, u32Bytes, rawIndex) ||
            !mapCopy(instance, stageBest, f32Bytes, rawBest) ||
            !mapCopy(instance, stageSecond, f32Bytes, rawSecond) ||
            !mapCopy(instance, stageViews, u32Bytes, rawViews) ||
            !mapCopy(instance, stageAccepted, u32Bytes, rawAccepted)) {
            [self fail:@"Dawn result readback failed"];
            return;
        }
        const auto* index32 = reinterpret_cast<const std::uint32_t*>(rawIndex.data());
        const auto* best = reinterpret_cast<const float*>(rawBest.data());
        const auto* second = reinterpret_cast<const float*>(rawSecond.data());
        const auto* views32 = reinterpret_cast<const std::uint32_t*>(rawViews.data());
        const auto* accepted32 = reinterpret_cast<const std::uint32_t*>(rawAccepted.data());
        std::vector<std::uint16_t> indices(pixels);
        std::vector<std::uint8_t> views(pixels), accepted(pixels);
        for (std::size_t index = 0; index < pixels; ++index) {
            indices[index] = static_cast<std::uint16_t>(index32[index]);
            views[index] = static_cast<std::uint8_t>(views32[index]);
            accepted[index] = static_cast<std::uint8_t>(accepted32[index]);
        }
        const auto parity = pocketworld::depth_sweep::evaluate_parity(
            pixels,
            static_cast<const std::uint16_t*>(expectedIndexData.bytes),
            static_cast<const float*>(expectedBestData.bytes),
            static_cast<const float*>(expectedSecondData.bytes),
            static_cast<const std::uint8_t*>(expectedViewsData.bytes),
            static_cast<const std::uint8_t*>(expectedAcceptedData.bytes),
            indices.data(), best, second, views.data(), accepted.data());
        NSDictionary* manifest = [NSJSONSerialization JSONObjectWithData:manifestData
            options:0 error:nil];
        NSDictionary* report = @{
            @"schema": @"pocketworld_model_free_depth_sweep_dawn_a16_bench_v1",
            @"status": parity.passes() ? @"complete" : @"failed",
            @"decision": parity.passes()
                ? @"PASS_DAWN_A16_MODEL_FREE_DEPTH_SWEEP_PARITY"
                : @"FAIL_DAWN_A16_MODEL_FREE_DEPTH_SWEEP_PARITY",
            @"device_model": machineIdentifier() ?: @"unknown",
            @"os_version": UIDevice.currentDevice.systemVersion,
            @"adapter": [NSString stringWithUTF8String:adapterName.c_str()],
            @"backend_contract": @"Dawn WGSL; Metal on Apple, Vulkan on Android/HarmonyOS",
            @"fixture_manifest": manifest,
            @"compile_ms": @(compileMs),
            @"warmup_ms": @(warmupMs),
            @"best_of_3_wall_ms": @(bestMs),
            @"runs": runs,
            @"parity": @{
                @"expected_accepted_pixels": manifest[@"expected"][@"accepted_pixels"],
                @"actual_accepted_pixels": @(parity.actual_accepted_pixels),
                @"accepted_mismatch_count": @(parity.accepted_mismatch_count),
                @"accepted_best_index_mismatch_count": @(
                    parity.accepted_best_index_mismatch_count),
                @"all_valid_best_index_mismatch_count": @(
                    parity.all_valid_best_index_mismatch_count),
                @"views_mismatch_count": @(parity.views_mismatch_count),
                @"valid_mismatch_count": @(parity.valid_mismatch_count),
                @"best_score_mean_abs": @(parity.best_score_mean_abs),
                @"best_score_max_abs": @(parity.best_score_max_abs),
                @"second_score_mean_abs": @(parity.second_score_mean_abs),
                @"second_score_max_abs": @(parity.second_score_max_abs),
            },
            @"peak_sampled_rss_bytes": @(residentBytes()),
            @"thermal_final": thermalStateName(NSProcessInfo.processInfo.thermalState),
            @"learned_model_consumed": @NO,
            @"third_party_matcher_output_consumed": @NO,
            @"lidar_or_scene_depth_consumed": @NO,
        };
        [self writeReport:report];
        [self setStatus:[NSString stringWithFormat:
            @"Dawn A16 %@\n\naccepted %lu/%@\ndepth/view mismatch %lu/%lu\nbest %.2f ms · RSS %.1f MB\nthermal %@",
            parity.passes() ? @"PASS" : @"FAIL",
            (unsigned long)parity.actual_accepted_pixels,
            manifest[@"expected"][@"accepted_pixels"],
            (unsigned long)parity.accepted_best_index_mismatch_count,
            (unsigned long)parity.views_mismatch_count,
            bestMs, residentBytes() / 1048576.0,
            thermalStateName(NSProcessInfo.processInfo.thermalState)]];
    }
}

@end
