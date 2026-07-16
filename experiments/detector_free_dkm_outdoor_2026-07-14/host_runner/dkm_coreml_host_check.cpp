#include "dkm_coreml_c_api.h"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace {

bool read_floats(const std::filesystem::path& path, std::vector<float>& values) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) return false;
    const auto bytes = stream.tellg();
    if (bytes < 0 || bytes % static_cast<std::streamoff>(sizeof(float)) != 0) {
        return false;
    }
    values.resize(static_cast<size_t>(bytes) / sizeof(float));
    stream.seekg(0);
    return static_cast<bool>(stream.read(
        reinterpret_cast<char*>(values.data()), bytes));
}

bool write_floats(
    const std::filesystem::path& path,
    const float* values,
    size_t count) {
    std::ofstream stream(path, std::ios::binary);
    stream.write(
        reinterpret_cast<const char*>(values),
        static_cast<std::streamsize>(count * sizeof(float)));
    return static_cast<bool>(stream);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 5 && argc != 6) {
        std::cerr << "usage: dkm_coreml_host_check MODEL.mlmodelc IMAGE0.f32 "
                     "IMAGE1.f32 OUTPUT_DIR [REPEATS]\n";
        return 64;
    }
    const int repeats = argc == 6 ? std::stoi(argv[5]) : 1;
    if (repeats < 1 || repeats > 100) {
        std::cerr << "REPEATS_OUT_OF_RANGE\n";
        return 64;
    }
    char error[1024] = {};
    pw_dkm_coreml_context* context = nullptr;
    int status = pw_dkm_coreml_create(argv[1], &context, error, sizeof(error));
    if (status != 0) {
        std::cerr << "CREATE_FAILED status=" << status << " error=" << error << '\n';
        return status;
    }
    const uint32_t width = pw_dkm_coreml_input_width(context);
    const uint32_t height = pw_dkm_coreml_input_height(context);
    std::vector<float> image0;
    std::vector<float> image1;
    if (!read_floats(argv[2], image0) || !read_floats(argv[3], image1)) {
        std::cerr << "INPUT_READ_FAILED\n";
        pw_dkm_coreml_destroy(context);
        return 65;
    }
    pw_dkm_coreml_result result{};
    std::vector<double> inference_seconds;
    for (int repeat = 0; repeat < repeats; ++repeat) {
        pw_dkm_coreml_result_release(&result);
        status = pw_dkm_coreml_predict(
            context,
            image0.data(),
            image1.data(),
            image0.size(),
            &result,
            error,
            sizeof(error));
        if (status != 0) {
            std::cerr << "PREDICT_FAILED status=" << status << " error=" << error << '\n';
            pw_dkm_coreml_destroy(context);
            return status;
        }
        inference_seconds.push_back(result.inference_seconds);
    }
    const std::filesystem::path output(argv[4]);
    std::filesystem::create_directories(output);
    const bool wrote =
        write_floats(output / "flow.f32", result.flow, result.flow_count) &&
        write_floats(
            output / "certainty.f32", result.certainty, result.certainty_count) &&
        write_floats(
            output / "low_certainty.f32",
            result.low_certainty,
            result.low_certainty_count);
    std::cout << "{\"status\":\"" << (wrote ? "PASS" : "WRITE_FAILED")
              << "\",\"width\":" << width
              << ",\"height\":" << height
              << ",\"input_count\":" << image0.size()
              << ",\"flow_count\":" << result.flow_count
              << ",\"certainty_count\":" << result.certainty_count
              << ",\"low_certainty_count\":" << result.low_certainty_count
              << ",\"inference_seconds\":[";
    for (size_t index = 0; index < inference_seconds.size(); ++index) {
        if (index) std::cout << ',';
        std::cout << inference_seconds[index];
    }
    std::cout << "]}\n";
    pw_dkm_coreml_result_release(&result);
    pw_dkm_coreml_destroy(context);
    return wrote ? 0 : 66;
}
