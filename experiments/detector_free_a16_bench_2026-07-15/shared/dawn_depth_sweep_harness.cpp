#include "portable_depth_contract.h"

#include "aether/render/dawn_gpu_device.h"
#include "aether/render/gpu_command.h"
#include "aether/render/gpu_device.h"

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <type_traits>
#include <vector>

namespace fs = std::filesystem;
using namespace aether::render;

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

template <typename T>
std::vector<T> read_binary(const fs::path& path) {
    static_assert(std::is_trivially_copyable_v<T>);
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) return {};
    const auto bytes = stream.tellg();
    if (bytes < 0 || bytes % static_cast<std::streamoff>(sizeof(T)) != 0) return {};
    std::vector<T> values(static_cast<std::size_t>(bytes) / sizeof(T));
    stream.seekg(0);
    stream.read(reinterpret_cast<char*>(values.data()), bytes);
    return stream ? values : std::vector<T>{};
}

GPUBufferHandle make_buffer(GPUDevice& device, std::size_t bytes,
                            GPUBufferUsage usage, const char* label) {
    GPUBufferDesc desc{};
    desc.size_bytes = bytes;
    desc.storage = GPUStorageMode::kPrivate;
    desc.usage_mask = static_cast<std::uint8_t>(usage);
    desc.label = label;
    return device.create_buffer(desc);
}

template <typename T>
std::vector<T> readback(GPUDevice& device, GPUBufferHandle source,
                        std::size_t count, const char* label) {
    GPUBufferDesc desc{};
    desc.size_bytes = count * sizeof(T);
    desc.storage = GPUStorageMode::kShared;
    desc.usage_mask = static_cast<std::uint8_t>(GPUBufferUsage::kStaging);
    desc.label = label;
    const auto staging = device.create_buffer(desc);
    if (!staging.valid() ||
        !dawn_copy_buffer_to_buffer(device, source, staging, desc.size_bytes)) {
        return {};
    }
    void* mapped = device.map_buffer(staging);
    if (!mapped) return {};
    std::vector<T> values(count);
    std::memcpy(values.data(), mapped, desc.size_bytes);
    device.unmap_buffer(staging);
    device.destroy_buffer(staging);
    return values;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "usage: %s EXPERIMENT_DIR\n", argv[0]);
        return EXIT_FAILURE;
    }
    const fs::path experiment = argv[1];
    const fs::path resources = experiment / "ios_bench/Resources";
    const fs::path shader_path = experiment / "shared/known_pose_depth_sweep.wgsl";

    const auto params_bytes = read_binary<std::uint8_t>(resources / "params.bin");
    const auto gray = read_binary<float>(resources / "gray_frames.f32");
    const auto projections = read_binary<float>(resources / "source_projections.f32");
    const auto expected_index = read_binary<std::uint16_t>(resources / "expected_best_index.u16");
    const auto expected_best = read_binary<float>(resources / "expected_best_score.f32");
    const auto expected_second = read_binary<float>(resources / "expected_second_score.f32");
    const auto expected_views = read_binary<std::uint8_t>(resources / "expected_views.u8");
    const auto expected_accepted = read_binary<std::uint8_t>(resources / "expected_accepted.u8");
    if (params_bytes.size() != sizeof(Params)) {
        std::fprintf(stderr, "FAIL params bytes=%zu\n", params_bytes.size());
        return EXIT_FAILURE;
    }
    Params params{};
    std::memcpy(&params, params_bytes.data(), sizeof(params));
    const std::size_t pixels = params.pixel_count;
    if (expected_index.size() != pixels || expected_best.size() != pixels ||
        expected_second.size() != pixels || expected_views.size() != pixels ||
        expected_accepted.size() != pixels) {
        std::fprintf(stderr, "FAIL fixture array size\n");
        return EXIT_FAILURE;
    }

    auto device = create_dawn_gpu_device(true);
    if (!device || device->backend() != GraphicsBackend::kDawn) {
        std::fprintf(stderr, "FAIL Dawn device\n");
        return EXIT_FAILURE;
    }
    if (!register_wgsl_from_file(*device, "known_pose_depth_sweep",
                                 shader_path.c_str())) {
        std::fprintf(stderr, "FAIL WGSL register\n");
        return EXIT_FAILURE;
    }
    const auto shader = device->load_shader(
        "known_pose_depth_sweep", GPUShaderStage::kCompute);
    const auto pipeline = shader.valid() ? device->create_compute_pipeline(shader)
                                         : GPUComputePipelineHandle{};
    if (!pipeline.valid()) {
        std::fprintf(stderr, "FAIL WGSL pipeline\n");
        return EXIT_FAILURE;
    }

    const auto gray_buffer = make_buffer(
        *device, gray.size() * sizeof(float), GPUBufferUsage::kStorage, "gray");
    const auto projection_buffer = make_buffer(
        *device, projections.size() * sizeof(float), GPUBufferUsage::kStorage, "projection");
    const auto params_buffer = make_buffer(
        *device, sizeof(params), GPUBufferUsage::kUniform, "params");
    const auto index_buffer = make_buffer(
        *device, pixels * sizeof(std::uint32_t), GPUBufferUsage::kStorage, "best_index");
    const auto best_buffer = make_buffer(
        *device, pixels * sizeof(float), GPUBufferUsage::kStorage, "best_score");
    const auto second_buffer = make_buffer(
        *device, pixels * sizeof(float), GPUBufferUsage::kStorage, "second_score");
    const auto views_buffer = make_buffer(
        *device, pixels * sizeof(std::uint32_t), GPUBufferUsage::kStorage, "views");
    const auto accepted_buffer = make_buffer(
        *device, pixels * sizeof(std::uint32_t), GPUBufferUsage::kStorage, "accepted");
    device->update_buffer(gray_buffer, gray.data(), 0, gray.size() * sizeof(float));
    device->update_buffer(projection_buffer, projections.data(), 0,
                          projections.size() * sizeof(float));
    device->update_buffer(params_buffer, &params, 0, sizeof(params));

    const auto started = std::chrono::steady_clock::now();
    auto command = device->create_command_buffer();
    auto* encoder = command ? command->make_compute_encoder() : nullptr;
    if (!encoder) {
        std::fprintf(stderr, "FAIL compute encoder\n");
        return EXIT_FAILURE;
    }
    encoder->set_pipeline(pipeline);
    encoder->set_buffer(gray_buffer, 0, 0);
    encoder->set_buffer(projection_buffer, 0, 1);
    encoder->set_buffer(params_buffer, 0, 2);
    encoder->set_buffer(index_buffer, 0, 3);
    encoder->set_buffer(best_buffer, 0, 4);
    encoder->set_buffer(second_buffer, 0, 5);
    encoder->set_buffer(views_buffer, 0, 6);
    encoder->set_buffer(accepted_buffer, 0, 7);
    encoder->dispatch_1d(params.pixel_count, 64);
    encoder->end_encoding();
    command->commit();
    command->wait_until_completed();
    const double wall_ms = std::chrono::duration<double, std::milli>(
        std::chrono::steady_clock::now() - started).count();
    if (command->had_error()) {
        std::fprintf(stderr, "FAIL GPU command\n");
        return EXIT_FAILURE;
    }

    const auto index_u32 = readback<std::uint32_t>(*device, index_buffer, pixels, "read_index");
    const auto best = readback<float>(*device, best_buffer, pixels, "read_best");
    const auto second = readback<float>(*device, second_buffer, pixels, "read_second");
    const auto views_u32 = readback<std::uint32_t>(*device, views_buffer, pixels, "read_views");
    const auto accepted_u32 = readback<std::uint32_t>(
        *device, accepted_buffer, pixels, "read_accepted");
    if (index_u32.size() != pixels || best.size() != pixels || second.size() != pixels ||
        views_u32.size() != pixels || accepted_u32.size() != pixels) {
        std::fprintf(stderr, "FAIL readback\n");
        return EXIT_FAILURE;
    }
    std::vector<std::uint16_t> index(pixels);
    std::vector<std::uint8_t> views(pixels), accepted(pixels);
    for (std::size_t i = 0; i < pixels; ++i) {
        index[i] = static_cast<std::uint16_t>(index_u32[i]);
        views[i] = static_cast<std::uint8_t>(views_u32[i]);
        accepted[i] = static_cast<std::uint8_t>(accepted_u32[i]);
    }
    const auto parity = pocketworld::depth_sweep::evaluate_parity(
        pixels, expected_index.data(), expected_best.data(), expected_second.data(),
        expected_views.data(), expected_accepted.data(), index.data(), best.data(),
        second.data(), views.data(), accepted.data());
    std::printf(
        "{\"status\":\"%s\",\"backend\":\"Dawn\",\"wall_ms\":%.6f,"
        "\"accepted\":%zu,\"accepted_mismatch\":%zu,"
        "\"accepted_depth_mismatch\":%zu,\"all_valid_depth_mismatch\":%zu,"
        "\"views_mismatch\":%zu,\"best_score_mean_abs\":%.9g,"
        "\"best_score_max_abs\":%.9g}\n",
        parity.passes() ? "PASS" : "FAIL", wall_ms,
        parity.actual_accepted_pixels, parity.accepted_mismatch_count,
        parity.accepted_best_index_mismatch_count,
        parity.all_valid_best_index_mismatch_count, parity.views_mismatch_count,
        parity.best_score_mean_abs, parity.best_score_max_abs);
    return parity.passes() ? EXIT_SUCCESS : EXIT_FAILURE;
}
