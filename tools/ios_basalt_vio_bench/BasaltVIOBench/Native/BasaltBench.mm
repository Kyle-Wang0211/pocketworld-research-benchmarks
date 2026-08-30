#include "BasaltBench.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <mach/mach_time.h>
#include <cmath>
#include <deque>
#include <fstream>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>
#include <unordered_map>

#if defined(PW_BASALT_CORE_LINKED) && PW_BASALT_CORE_LINKED
#include <cereal/archives/json.hpp>
#include <basalt/calibration/calibration.hpp>
#include <basalt/io/dataset_io.h>
#include <basalt/optical_flow/optical_flow.h>
#include <basalt/serialization/headers_serialization.h>
#include <basalt/utils/imu_types.h>
#include <basalt/utils/vio_config.h>
#include <basalt/vi_estimator/sqrt_keypoint_vio.h>
#include <basalt/vi_estimator/vio_estimator.h>
#include <tbb/global_control.h>
#endif

namespace {

// The bench has exactly one monotonic domain: mach_absolute_time nanoseconds.
//
// std::chrono::steady_clock must never be used here. On Darwin libc++ maps it to
// clock_gettime(CLOCK_MONOTONIC), which is mach_continuous_time and *includes*
// the time the device spent asleep. Both Swift-side clocks the bench feeds us --
// CMClockGetHostTimeClock() for camera presentation timestamps and
// DispatchTime.uptimeNanoseconds for run start -- are mach_absolute_time, which
// *excludes* sleep. Subtracting across the two domains yields the entire sleep
// accumulation as a constant offset rather than a latency.
//
// Measured on Darwin 2026-08-30 (timebase numer=125 denom=3):
//   std::chrono::steady_clock  43147376131416 ns  (11.985 h)  == mach_continuous_time
//   mach_absolute_time         42087301077208 ns  (11.691 h)  == CLOCK_UPTIME_RAW
// The 0.294 h gap is sleep. On a phone left idle overnight the same defect
// reported an 81,219,463 ms P95 pipeline latency in a 97 s run.
//
// mach_absolute_time() returns timebase ticks, not nanoseconds (24 MHz on arm64,
// numer/denom = 125/3), so the timebase conversion is mandatory.
uint64_t monotonic_now_ns() {
    static const mach_timebase_info_data_t timebase = [] {
        mach_timebase_info_data_t info{};
        mach_timebase_info(&info);
        return info;
    }();
    return mach_absolute_time() * timebase.numer / timebase.denom;
}

[[maybe_unused]] uint32_t saturating_queue_size(std::ptrdiff_t value) {
    if (value <= 0) return 0;
    const auto maximum = static_cast<std::ptrdiff_t>(
        std::numeric_limits<uint32_t>::max());
    return static_cast<uint32_t>(std::min(value, maximum));
}

[[maybe_unused]] void update_peak(uint32_t value, uint32_t &peak) {
    peak = std::max(value, peak);
}

bool finite3(double x, double y, double z) {
    return std::isfinite(x) && std::isfinite(y) && std::isfinite(z);
}

std::atomic_bool g_stop_requested{false};
std::mutex g_active_mutex;
basalt_bench_t *g_active_bench = nullptr;

}  // namespace

struct basalt_bench {
    mutable std::mutex mutex;
    basalt_bench_phase_t phase = BASALT_BENCH_PHASE_RUNNING;
    std::atomic_bool stop_requested{false};
    int64_t last_camera_timestamp_ns = std::numeric_limits<int64_t>::min();
    int64_t last_imu_timestamp_ns = std::numeric_limits<int64_t>::min();
    int64_t last_output_timestamp_ns = std::numeric_limits<int64_t>::min();
    uint32_t pose_queue_capacity = 1024;
    uint32_t optical_flow_input_queue_capacity = 0;
    uint32_t vio_imu_queue_capacity = 0;
    uint32_t optical_flow_input_queue_peak = 0;
    uint32_t vio_vision_queue_peak = 0;
    uint32_t vio_imu_queue_peak = 0;
    uint32_t bridge_pose_queue_peak = 0;
    basalt_bench_counters_t counters{};
    std::deque<basalt_bench_pose_t> poses;
    std::unordered_map<int64_t, uint64_t> camera_accept_times;
    std::thread output_thread;

#if defined(PW_BASALT_CORE_LINKED) && PW_BASALT_CORE_LINKED
    basalt::VioConfig config;
    basalt::Calibration<double> calibration;
    basalt::OpticalFlowBase::Ptr optical_flow;
    basalt::VioEstimatorBase::Ptr estimator;
    tbb::concurrent_bounded_queue<basalt::OpticalFlowResult::Ptr>
        orphan_vision_queue;
    tbb::concurrent_bounded_queue<basalt::PoseVelBiasState<double>::Ptr>
        output_queue;
#endif
};

namespace {

#if defined(PW_BASALT_CORE_LINKED) && PW_BASALT_CORE_LINKED

bool load_calibration(const char *path,
                      basalt::Calibration<double> &calibration) {
    std::ifstream input(path, std::ios::binary);
    if (!input.is_open()) return false;
    cereal::JSONInputArchive archive(input);
    archive(calibration);
    return true;
}

bool calibration_shape_is_valid(
    const basalt::Calibration<double> &calibration) {
    const size_t count = calibration.intrinsics.size();
    if (count == 0 || calibration.T_i_c.size() != count ||
        calibration.resolution.size() != count) {
        return false;
    }
    for (const auto &resolution : calibration.resolution) {
        if (resolution.x() <= 0 || resolution.y() <= 0) return false;
    }
    return true;
}

bool pose_is_finite(const basalt::PoseVelBiasState<double> &state) {
    return state.T_w_i.matrix().allFinite() && state.vel_w_i.allFinite() &&
           state.bias_gyro.allFinite() && state.bias_accel.allFinite();
}

basalt_bench_pose_t make_pose_receipt(
    const basalt::PoseVelBiasState<double> &state,
    uint64_t accepted_ns,
    uint64_t output_ns) {
    basalt_bench_pose_t receipt{};
    receipt.timestamp_ns = state.t_ns;
    const Eigen::Matrix4d matrix = state.T_w_i.matrix();
    for (int row = 0; row < 4; ++row) {
        for (int col = 0; col < 4; ++col) {
            receipt.T_w_i[row * 4 + col] = matrix(row, col);
        }
    }
    const Eigen::Quaterniond quaternion = state.T_w_i.unit_quaternion();
    receipt.quaternion_xyzw[0] = quaternion.x();
    receipt.quaternion_xyzw[1] = quaternion.y();
    receipt.quaternion_xyzw[2] = quaternion.z();
    receipt.quaternion_xyzw[3] = quaternion.w();
    for (int i = 0; i < 3; ++i) {
        receipt.translation_xyz[i] = state.T_w_i.translation()[i];
        receipt.velocity_xyz[i] = state.vel_w_i[i];
        receipt.gyro_bias_xyz[i] = state.bias_gyro[i];
        receipt.accel_bias_xyz[i] = state.bias_accel[i];
    }
    receipt.camera_accepted_monotonic_ns = accepted_ns;
    receipt.output_monotonic_ns = output_ns;
    if (accepted_ns != 0 && output_ns >= accepted_ns) {
        receipt.pipeline_latency_ns = output_ns - accepted_ns;
    }
    return receipt;
}

void consume_outputs(basalt_bench *bench) {
    while (true) {
        basalt::PoseVelBiasState<double>::Ptr state;
        bench->output_queue.pop(state);
        std::lock_guard<std::mutex> lock(bench->mutex);
        if (!state) {
            ++bench->counters.pose_eof_sentinels_received;
            break;
        }
        if (!pose_is_finite(*state)) {
            ++bench->counters.nonfinite_pose_rejected;
            continue;
        }
        const uint64_t output_ns = monotonic_now_ns();
        uint64_t accepted_ns = 0;
        const auto accepted = bench->camera_accept_times.find(state->t_ns);
        if (accepted != bench->camera_accept_times.end()) {
            accepted_ns = accepted->second;
            bench->camera_accept_times.erase(accepted);
        }
        basalt_bench_pose_t receipt =
            make_pose_receipt(*state, accepted_ns, output_ns);
        ++bench->counters.poses_produced;
        bench->last_output_timestamp_ns = state->t_ns;
        if (receipt.pipeline_latency_ns != 0) {
            bench->counters.pipeline_latency_ns_total +=
                receipt.pipeline_latency_ns;
            bench->counters.pipeline_latency_ns_max = std::max(
                bench->counters.pipeline_latency_ns_max,
                receipt.pipeline_latency_ns);
        }
        if (bench->poses.size() == bench->pose_queue_capacity) {
            bench->poses.pop_front();
            ++bench->counters.poses_dropped_bridge_queue;
        }
        bench->poses.push_back(receipt);
        update_peak(static_cast<uint32_t>(bench->poses.size()),
                    bench->bridge_pose_queue_peak);
    }
}

void update_official_queue_peaks_locked(basalt_bench *bench) {
    update_peak(saturating_queue_size(bench->optical_flow->input_queue.size()),
                bench->optical_flow_input_queue_peak);
    update_peak(saturating_queue_size(bench->estimator->vision_data_queue.size()),
                bench->vio_vision_queue_peak);
    update_peak(saturating_queue_size(bench->estimator->imu_data_queue.size()),
                bench->vio_imu_queue_peak);
}

basalt_bench_status_t seal_locked(basalt_bench *bench) {
    if (bench->phase == BASALT_BENCH_PHASE_SEALED ||
        bench->phase == BASALT_BENCH_PHASE_DRAINING ||
        bench->phase == BASALT_BENCH_PHASE_DRAINED ||
        bench->phase == BASALT_BENCH_PHASE_STOPPED) {
        return BASALT_BENCH_OK;
    }
    if (bench->phase != BASALT_BENCH_PHASE_RUNNING) {
        return BASALT_BENCH_INVALID_STATE;
    }
    /* EOF is deliberately queued behind every officially accepted sample. */
    bench->optical_flow->input_queue.push(nullptr);
    ++bench->counters.image_eof_sentinels_sent;
    bench->estimator->imu_data_queue.push(nullptr);
    ++bench->counters.imu_eof_sentinels_sent;
    bench->phase = BASALT_BENCH_PHASE_SEALED;
    update_official_queue_peaks_locked(bench);
    return BASALT_BENCH_OK;
}

#endif

}  // namespace

int basalt_bench_backend_available(void) {
#if defined(PW_BASALT_CORE_LINKED) && PW_BASALT_CORE_LINKED
    return 1;
#else
    return 0;
#endif
}

basalt_bench_status_t basalt_bench_create(
    const basalt_bench_create_options_t *options,
    basalt_bench_t **out_bench) {
    if (!out_bench) return BASALT_BENCH_INVALID_ARGUMENT;
    *out_bench = nullptr;
    if (!options ||
        options->struct_size < sizeof(basalt_bench_create_options_t) ||
        !options->config_path || options->config_path[0] == '\0' ||
        !options->calibration_path || options->calibration_path[0] == '\0') {
        return BASALT_BENCH_INVALID_ARGUMENT;
    }
#if !defined(PW_BASALT_CORE_LINKED) || !PW_BASALT_CORE_LINKED
    return BASALT_BENCH_BACKEND_UNAVAILABLE;
#else
    std::ifstream config_file(options->config_path);
    std::ifstream calibration_file(options->calibration_path);
    if (!config_file.is_open() || !calibration_file.is_open()) {
        return BASALT_BENCH_IO_ERROR;
    }
    std::unique_lock<std::mutex> active_lock(g_active_mutex);
    if (g_active_bench != nullptr) return BASALT_BENCH_INVALID_STATE;
    std::unique_ptr<basalt_bench> bench(new basalt_bench);
    bench->pose_queue_capacity = options->pose_queue_capacity == 0
                                     ? 1024
                                     : options->pose_queue_capacity;
    try {
        bench->config.load(options->config_path);
        if (!load_calibration(options->calibration_path,
                              bench->calibration) ||
            !calibration_shape_is_valid(bench->calibration)) {
            return BASALT_BENCH_CONFIG_ERROR;
        }
        bench->optical_flow = basalt::OpticalFlowFactory::getOpticalFlow(
            bench->config, bench->calibration);
        if (!bench->optical_flow) {
            throw std::runtime_error("official optical flow factory failed");
        }
        /* Keep OpticalFlow destruction safe even if VIO factory creation fails. */
        bench->optical_flow->output_queue = &bench->orphan_vision_queue;
        /*
         * Exact expansion of upstream VioEstimatorFactory for
         * use_imu=true/use_double=false. The iOS VIO-only archive excludes
         * vio_estimator.cpp because its other branch pulls the VO estimator.
         */
        bench->estimator =
            std::make_shared<basalt::SqrtKeypointVioEstimator<float>>(
                basalt::constants::g, bench->calibration, bench->config);
        if (!bench->estimator) {
            throw std::runtime_error("official VIO factory failed");
        }
        bench->optical_flow_input_queue_capacity = saturating_queue_size(
            bench->optical_flow->input_queue.capacity());
        bench->vio_imu_queue_capacity = saturating_queue_size(
            bench->estimator->imu_data_queue.capacity());
        /* Preserve upstream src/vio.cpp factory/initialize/wiring order. */
        bench->estimator->initialize(Eigen::Vector3d::Zero(),
                                     Eigen::Vector3d::Zero());
        bench->optical_flow->output_queue =
            &bench->estimator->vision_data_queue;
        bench->estimator->out_state_queue = &bench->output_queue;
        bench->output_thread = std::thread(consume_outputs, bench.get());
    } catch (...) {
        if (bench->optical_flow) {
            bench->optical_flow->input_queue.push(nullptr);
        }
        if (bench->estimator) {
            bench->estimator->imu_data_queue.push(nullptr);
            bench->estimator->maybe_join();
            bench->estimator->drain_input_queues();
        }
        if (bench->output_thread.joinable()) bench->output_thread.join();
        bench->optical_flow.reset();
        bench->estimator.reset();
        return BASALT_BENCH_CONFIG_ERROR;
    }
    g_stop_requested.store(false, std::memory_order_release);
    g_active_bench = bench.get();
    active_lock.unlock();
    *out_bench = bench.release();
    return BASALT_BENCH_OK;
#endif
}

basalt_bench_status_t basalt_bench_submit_camera(
    basalt_bench_t *bench,
    int64_t timestamp_ns,
    const basalt_bench_image_plane_t *planes,
    size_t plane_count,
    uint64_t accepted_monotonic_ns) {
    if (!bench || !planes || plane_count == 0 || timestamp_ns < 0) {
        return BASALT_BENCH_INVALID_ARGUMENT;
    }
#if !defined(PW_BASALT_CORE_LINKED) || !PW_BASALT_CORE_LINKED
    (void)accepted_monotonic_ns;
    return BASALT_BENCH_BACKEND_UNAVAILABLE;
#else
    const uint64_t copy_start_ns = monotonic_now_ns();
    basalt::OpticalFlowInput::Ptr input(new basalt::OpticalFlowInput);
    input->t_ns = timestamp_ns;
    input->img_data.resize(plane_count);
    uint64_t copied_bytes = 0;
    {
        std::lock_guard<std::mutex> lock(bench->mutex);
        ++bench->counters.camera_offered;
        if (bench->phase != BASALT_BENCH_PHASE_RUNNING ||
            bench->stop_requested.load(std::memory_order_acquire) ||
            g_stop_requested.load(std::memory_order_acquire)) {
            ++bench->counters.camera_rejected_sealed;
            return BASALT_BENCH_INPUT_SEALED;
        }
        if (timestamp_ns <= bench->last_camera_timestamp_ns) {
            ++bench->counters.camera_rejected_timestamp;
            return BASALT_BENCH_TIMESTAMP_REGRESSION;
        }
        if (plane_count != bench->calibration.resolution.size()) {
            return BASALT_BENCH_INVALID_ARGUMENT;
        }
        for (size_t camera = 0; camera < plane_count; ++camera) {
            const auto &plane = planes[camera];
            const auto &resolution = bench->calibration.resolution[camera];
            if (!plane.pixels || plane.width == 0 || plane.height == 0 ||
                plane.bytes_per_row < plane.width ||
                plane.width != static_cast<uint32_t>(resolution.x()) ||
                plane.height != static_cast<uint32_t>(resolution.y())) {
                return BASALT_BENCH_INVALID_ARGUMENT;
            }
        }
    }
    for (size_t camera = 0; camera < plane_count; ++camera) {
        const auto &plane = planes[camera];
        basalt::ImageData &image_data = input->img_data[camera];
        image_data.exposure = 0;
        image_data.img.reset(
            new basalt::ManagedImage<uint16_t>(plane.width, plane.height));
        for (uint32_t row = 0; row < plane.height; ++row) {
            const uint8_t *source =
                plane.pixels + static_cast<size_t>(row) * plane.bytes_per_row;
            uint16_t *destination = image_data.img->RowPtr(row);
            for (uint32_t col = 0; col < plane.width; ++col) {
                destination[col] = static_cast<uint16_t>(source[col]) << 8;
            }
        }
        copied_bytes += static_cast<uint64_t>(plane.width) * plane.height;
    }
    const uint64_t copy_duration_ns = monotonic_now_ns() - copy_start_ns;
    std::lock_guard<std::mutex> lock(bench->mutex);
    if (bench->phase != BASALT_BENCH_PHASE_RUNNING ||
        bench->stop_requested.load(std::memory_order_acquire) ||
        g_stop_requested.load(std::memory_order_acquire)) {
        ++bench->counters.camera_rejected_sealed;
        return BASALT_BENCH_INPUT_SEALED;
    }
    if (timestamp_ns <= bench->last_camera_timestamp_ns) {
        ++bench->counters.camera_rejected_timestamp;
        return BASALT_BENCH_TIMESTAMP_REGRESSION;
    }
    if (!bench->optical_flow->input_queue.try_push(input)) {
        ++bench->counters.camera_dropped_queue_full;
        update_official_queue_peaks_locked(bench);
        return BASALT_BENCH_QUEUE_FULL;
    }
    bench->last_camera_timestamp_ns = timestamp_ns;
    ++bench->counters.camera_accepted;
    bench->counters.camera_bytes_copied += copied_bytes;
    bench->counters.camera_copy_service_ns_total += copy_duration_ns;
    bench->counters.camera_copy_service_ns_max = std::max(
        bench->counters.camera_copy_service_ns_max, copy_duration_ns);
    if (accepted_monotonic_ns == 0) accepted_monotonic_ns = monotonic_now_ns();
    bench->camera_accept_times[timestamp_ns] = accepted_monotonic_ns;
    update_official_queue_peaks_locked(bench);
    return BASALT_BENCH_OK;
#endif
}

basalt_bench_status_t basalt_bench_submit_imu(
    basalt_bench_t *bench,
    int64_t timestamp_ns,
    double accel_x,
    double accel_y,
    double accel_z,
    double gyro_x,
    double gyro_y,
    double gyro_z) {
    if (!bench || timestamp_ns < 0 || !finite3(accel_x, accel_y, accel_z) ||
        !finite3(gyro_x, gyro_y, gyro_z)) {
        return BASALT_BENCH_INVALID_ARGUMENT;
    }
#if !defined(PW_BASALT_CORE_LINKED) || !PW_BASALT_CORE_LINKED
    return BASALT_BENCH_BACKEND_UNAVAILABLE;
#else
    basalt::ImuData<double>::Ptr input(new basalt::ImuData<double>);
    input->t_ns = timestamp_ns;
    input->accel = Eigen::Vector3d(accel_x, accel_y, accel_z);
    input->gyro = Eigen::Vector3d(gyro_x, gyro_y, gyro_z);
    std::lock_guard<std::mutex> lock(bench->mutex);
    ++bench->counters.imu_offered;
    if (bench->phase != BASALT_BENCH_PHASE_RUNNING ||
        bench->stop_requested.load(std::memory_order_acquire) ||
        g_stop_requested.load(std::memory_order_acquire)) {
        ++bench->counters.imu_rejected_sealed;
        return BASALT_BENCH_INPUT_SEALED;
    }
    if (timestamp_ns <= bench->last_imu_timestamp_ns) {
        ++bench->counters.imu_rejected_timestamp;
        return BASALT_BENCH_TIMESTAMP_REGRESSION;
    }
    if (!bench->estimator->imu_data_queue.try_push(input)) {
        ++bench->counters.imu_dropped_queue_full;
        update_official_queue_peaks_locked(bench);
        return BASALT_BENCH_QUEUE_FULL;
    }
    bench->last_imu_timestamp_ns = timestamp_ns;
    ++bench->counters.imu_accepted;
    update_official_queue_peaks_locked(bench);
    return BASALT_BENCH_OK;
#endif
}

basalt_bench_status_t basalt_bench_poll_pose(
    basalt_bench_t *bench,
    basalt_bench_pose_t *out_pose) {
    if (!bench || !out_pose) return BASALT_BENCH_INVALID_ARGUMENT;
#if !defined(PW_BASALT_CORE_LINKED) || !PW_BASALT_CORE_LINKED
    return BASALT_BENCH_BACKEND_UNAVAILABLE;
#else
    std::lock_guard<std::mutex> lock(bench->mutex);
    if (!bench->poses.empty()) {
        *out_pose = bench->poses.front();
        bench->poses.pop_front();
        ++bench->counters.poses_polled;
        return BASALT_BENCH_OK;
    }
    if (bench->counters.pose_eof_sentinels_received != 0) {
        return BASALT_BENCH_END_OF_STREAM;
    }
    return BASALT_BENCH_NO_OUTPUT;
#endif
}

basalt_bench_status_t basalt_bench_seal_inputs(basalt_bench_t *bench) {
    if (!bench) return BASALT_BENCH_INVALID_ARGUMENT;
#if !defined(PW_BASALT_CORE_LINKED) || !PW_BASALT_CORE_LINKED
    return BASALT_BENCH_BACKEND_UNAVAILABLE;
#else
    std::lock_guard<std::mutex> lock(bench->mutex);
    return seal_locked(bench);
#endif
}

basalt_bench_status_t basalt_bench_drain(basalt_bench_t *bench) {
    if (!bench) return BASALT_BENCH_INVALID_ARGUMENT;
#if !defined(PW_BASALT_CORE_LINKED) || !PW_BASALT_CORE_LINKED
    return BASALT_BENCH_BACKEND_UNAVAILABLE;
#else
    {
        std::lock_guard<std::mutex> lock(bench->mutex);
        if (bench->phase == BASALT_BENCH_PHASE_DRAINED ||
            bench->phase == BASALT_BENCH_PHASE_STOPPED) {
            return BASALT_BENCH_OK;
        }
        if (bench->phase != BASALT_BENCH_PHASE_SEALED) {
            return BASALT_BENCH_INVALID_STATE;
        }
        bench->phase = BASALT_BENCH_PHASE_DRAINING;
    }
    /* Exact official offline order from upstream src/vio.cpp. */
    bench->estimator->maybe_join();
    bench->estimator->drain_input_queues();
    if (bench->output_thread.joinable()) bench->output_thread.join();
    {
        std::lock_guard<std::mutex> lock(bench->mutex);
        bench->phase = BASALT_BENCH_PHASE_DRAINED;
        update_official_queue_peaks_locked(bench);
    }
    return BASALT_BENCH_OK;
#endif
}

basalt_bench_status_t basalt_bench_stop(basalt_bench_t *bench) {
    if (!bench) return BASALT_BENCH_INVALID_ARGUMENT;
#if !defined(PW_BASALT_CORE_LINKED) || !PW_BASALT_CORE_LINKED
    return BASALT_BENCH_BACKEND_UNAVAILABLE;
#else
    {
        std::lock_guard<std::mutex> lock(bench->mutex);
        if (bench->phase == BASALT_BENCH_PHASE_STOPPED) {
            return BASALT_BENCH_OK;
        }
        if (bench->phase != BASALT_BENCH_PHASE_DRAINED) {
            return BASALT_BENCH_INVALID_STATE;
        }
    }
    /* OpticalFlow's official destructor joins its processing worker. */
    bench->optical_flow.reset();
    bench->estimator.reset();
    {
        std::lock_guard<std::mutex> lock(bench->mutex);
        bench->phase = BASALT_BENCH_PHASE_STOPPED;
    }
    return BASALT_BENCH_OK;
#endif
}

basalt_bench_status_t basalt_bench_get_snapshot(
    basalt_bench_t *bench,
    basalt_bench_snapshot_t *out_snapshot) {
    if (!bench || !out_snapshot) return BASALT_BENCH_INVALID_ARGUMENT;
#if !defined(PW_BASALT_CORE_LINKED) || !PW_BASALT_CORE_LINKED
    return BASALT_BENCH_BACKEND_UNAVAILABLE;
#else
    std::lock_guard<std::mutex> lock(bench->mutex);
    basalt_bench_snapshot_t snapshot{};
    snapshot.phase = bench->phase;
    snapshot.stop_requested =
        bench->stop_requested.load(std::memory_order_acquire) ||
        g_stop_requested.load(std::memory_order_acquire);
    snapshot.last_camera_timestamp_ns = bench->last_camera_timestamp_ns;
    snapshot.last_imu_timestamp_ns = bench->last_imu_timestamp_ns;
    snapshot.last_output_timestamp_ns = bench->last_output_timestamp_ns;
    if (bench->optical_flow) {
        snapshot.optical_flow_input_queue_size = saturating_queue_size(
            bench->optical_flow->input_queue.size());
    }
    snapshot.optical_flow_input_queue_capacity =
        bench->optical_flow_input_queue_capacity;
    if (bench->estimator) {
        snapshot.vio_vision_queue_size = saturating_queue_size(
            bench->estimator->vision_data_queue.size());
        snapshot.vio_imu_queue_size =
            saturating_queue_size(bench->estimator->imu_data_queue.size());
    }
    snapshot.vio_imu_queue_capacity = bench->vio_imu_queue_capacity;
    snapshot.bridge_pose_queue_size =
        static_cast<uint32_t>(bench->poses.size());
    snapshot.optical_flow_input_queue_peak =
        bench->optical_flow_input_queue_peak;
    snapshot.vio_vision_queue_peak = bench->vio_vision_queue_peak;
    snapshot.vio_imu_queue_peak = bench->vio_imu_queue_peak;
    snapshot.bridge_pose_queue_peak = bench->bridge_pose_queue_peak;
    snapshot.observed_tbb_active_parallelism = static_cast<uint32_t>(
        std::min<size_t>(
            tbb::global_control::active_value(
                tbb::global_control::max_allowed_parallelism),
            std::numeric_limits<uint32_t>::max()));
    snapshot.counters = bench->counters;
    *out_snapshot = snapshot;
    return BASALT_BENCH_OK;
#endif
}

void basalt_bench_request_stop_for_run(basalt_bench_t *bench) {
    if (bench) bench->stop_requested.store(true, std::memory_order_release);
}

int basalt_bench_stop_requested(const basalt_bench_t *bench) {
    if (!bench) return 1;
    return (bench->stop_requested.load(std::memory_order_acquire) ||
            g_stop_requested.load(std::memory_order_acquire))
               ? 1
               : 0;
}

void basalt_bench_request_stop(void) {
    g_stop_requested.store(true, std::memory_order_release);
    std::lock_guard<std::mutex> lock(g_active_mutex);
    if (g_active_bench) {
        g_active_bench->stop_requested.store(true, std::memory_order_release);
    }
}

void basalt_bench_destroy(basalt_bench_t *bench) {
    if (!bench) return;
#if defined(PW_BASALT_CORE_LINKED) && PW_BASALT_CORE_LINKED
    basalt_bench_seal_inputs(bench);
    basalt_bench_drain(bench);
    basalt_bench_stop(bench);
    {
        std::lock_guard<std::mutex> lock(g_active_mutex);
        if (g_active_bench == bench) g_active_bench = nullptr;
    }
#endif
    delete bench;
}

const char *basalt_bench_status_name(basalt_bench_status_t status) {
    switch (status) {
        case BASALT_BENCH_OK: return "ok";
        case BASALT_BENCH_INVALID_ARGUMENT: return "invalid_argument";
        case BASALT_BENCH_BACKEND_UNAVAILABLE: return "backend_unavailable";
        case BASALT_BENCH_IO_ERROR: return "io_error";
        case BASALT_BENCH_CONFIG_ERROR: return "config_error";
        case BASALT_BENCH_INVALID_STATE: return "invalid_state";
        case BASALT_BENCH_TIMESTAMP_REGRESSION:
            return "timestamp_regression";
        case BASALT_BENCH_QUEUE_FULL: return "queue_full";
        case BASALT_BENCH_INPUT_SEALED: return "input_sealed";
        case BASALT_BENCH_NO_OUTPUT: return "no_output";
        case BASALT_BENCH_END_OF_STREAM: return "end_of_stream";
        case BASALT_BENCH_INTERNAL_ERROR: return "internal_error";
    }
    return "unknown";
}
