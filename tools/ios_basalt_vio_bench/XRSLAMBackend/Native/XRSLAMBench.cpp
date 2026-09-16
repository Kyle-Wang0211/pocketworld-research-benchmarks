#include <cstdio>
// The per-frame cost at the production resolution is dominated by two OpenCV
// calls inside upstream's OpenCvImage::preprocess -- CLAHE over the whole frame
// and buildOpticalFlowPyramid with derivatives. Both go through
// cv::parallel_for_, so how many threads OpenCV believes it has decides whether
// that work uses one core or all of them. Nothing in this tree ever set or
// reported it.
#include <opencv2/core.hpp>
#include <string>
#include <sstream>
#include <fstream>
#include "XRSLAMBench.h"
#include "XRSLAMBenchTesting.hpp"

#include <algorithm>
#include <array>
#include <deque>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <limits>
#include <mutex>
#include <new>
#include <utility>
#include <vector>

#if defined(PW_XRSLAM_CORE_LINKED) && PW_XRSLAM_CORE_LINKED
#include <opencv2/calib3d.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>
#endif

/* The C-compatible frozen declaration mirror is copied byte-for-byte from the
 * archive receipt directory. These asserts pin the exact arm64 upstream ABI
 * consumed by libxrslam_generic_4beb1a9.a. */
static_assert(sizeof(XRSLAMSensorType) == 4);
static_assert(sizeof(XRSLAMResultType) == 4);
static_assert(sizeof(XRSLAMState) == 4);
static_assert(sizeof(XRSLAMImageExtension) == 32);
static_assert(sizeof(XRSLAMImage) == 40);
static_assert(offsetof(XRSLAMImage, data) == 0);
static_assert(offsetof(XRSLAMImage, timeStamp) == 8);
static_assert(offsetof(XRSLAMImage, stride) == 16);
static_assert(offsetof(XRSLAMImage, camera_id) == 20);
static_assert(offsetof(XRSLAMImage, channel) == 24);
static_assert(offsetof(XRSLAMImage, ext) == 32);
static_assert(sizeof(XRSLAMDepthImage) == 24);
static_assert(sizeof(XRSLAMAcceleration) == 32);
static_assert(offsetof(XRSLAMAcceleration, timestamp) == 24);
static_assert(sizeof(XRSLAMGyroscope) == 32);
static_assert(offsetof(XRSLAMGyroscope, timestamp) == 24);
static_assert(sizeof(XRSLAMGravity) == 32);
static_assert(sizeof(XRSLAMRotationVector) == 40);
static_assert(sizeof(XRSLAMPose) == 64);
static_assert(offsetof(XRSLAMPose, quaternion) == 0);
static_assert(offsetof(XRSLAMPose, translation) == 32);
static_assert(offsetof(XRSLAMPose, timestamp) == 56);
static_assert(sizeof(XRSLAMIntrinsics) == 32);
static_assert(sizeof(XRSLAMBias) == 24);
static_assert(sizeof(XRSLAMIMUBias) == 48);
static_assert(XRSLAM_SENSOR_CAMERA == 0);

/* Reads a whole config file. XRSLAMCreate takes the text, not the path. */
static std::string read_file(const char *path) {
  if (path == nullptr || path[0] == '\0') return {};
  std::ifstream stream(path, std::ios::in | std::ios::binary);
  if (!stream) return {};
  std::ostringstream buffer;
  buffer << stream.rdbuf();
  return buffer.str();
}
static_assert(XRSLAM_SENSOR_ACCELERATION == 2);
static_assert(XRSLAM_SENSOR_GYROSCOPE == 3);
static_assert(XRSLAM_RESULT_BODY_POSE == 0);
static_assert(XRSLAM_RESULT_STATE == 2);
static_assert(XRSLAM_STATE_INITIALIZING == 0);
static_assert(XRSLAM_STATE_TRACKING_SUCCESS == 1);
static_assert(XRSLAM_STATE_TRACKING_FAIL == 2);

/// Read-only backlog accessor added to the vendored XRSLAM by
/// xrslam_pending_worker_frames.patch. Declared here rather than in the frozen
/// XRSLAM.h so the public ABI header stays byte-identical to upstream's.
extern "C" int XRSLAMGetPendingWorkerFrames(void);
/// [2026-09-09] The IMU-propagated pose. Upstream's core already returns it from
/// Detail::track_gyroscope / track_accelerometer (both `return predict_pose(t)`); the C interface
/// discarded that value, so XRSLAM_RESULT_BODY_POSE could only advance once per image. Declared here
/// for the same reason as the accessors above: the frozen XRSLAM.h stays byte-identical to upstream.
extern "C" void XRSLAMGetPropagatedPose(XRSLAMPose *pose);
/// [2026-09-09] Initialisation exit counts, read-only. See xrslam_bench_counters_t.
extern "C" void XRSLAMGetInitCounters(unsigned long long *out, int count);
/// VINS-Mono's Estimator::failureDetection criteria, ported verbatim into the
/// vendored XRSLAM and exposed read-only. Upstream XRSLAM reports no health at
/// all -- SYS_CRASH is never assigned -- so a consumer had no way to tell a
/// good pose from one produced by a diverged estimator. Bit 1 accelerometer
/// bias, 2 gyroscope bias, 4 translation jump, 8 vertical jump.
extern "C" int XRSLAMGetDivergenceFlags(void);
/// Seconds the divergence condition has held. ORB-SLAM3 treats a lost frame as
/// RECENTLY_LOST and only escalates to LOST once it has held for
/// time_recently_lost, 5.0 s in the inertial case; an isolated hit is not a
/// failure. Reported, not acted on.
extern "C" double XRSLAMGetDivergenceSustainedSeconds(void);
/// How many IMU samples and camera frames actually reached the estimator,
/// added by xrslam_pending_worker_frames.patch. Upstream drops unpaired
/// accelerometer and gyroscope samples silently, so a live run starved of IMU
/// looks exactly like one that cannot track; these separate the two.
extern "C" void XRSLAMGetIngestCounts(unsigned long long *imu,
                                      unsigned long long *camera);

// Weak fallbacks so this bench links against a vendored XRSLAM that carries the
// observability patches and against one that does not -- which is what makes an
// A/B between the two archives possible at all. A strong definition in the
// archive wins; without one these report nothing rather than failing to link.
extern "C" __attribute__((weak)) int XRSLAMGetPendingWorkerFrames(void) {
  return 0;
}
extern "C" __attribute__((weak)) int XRSLAMGetDivergenceFlags(void) { return 0; }
extern "C" __attribute__((weak)) double XRSLAMGetDivergenceSustainedSeconds(void) {
  return 0.0;
}
extern "C" __attribute__((weak)) void
XRSLAMGetIngestCounts(unsigned long long *imu, unsigned long long *camera) {
  if (imu)
    *imu = 0;
  if (camera)
    *camera = 0;
}
// [pw] 2026-09-15 这两个此前漏掉了,于是台架**只能**链 gpufe 那一个归档
// (它是唯一导出这两个符号的):generic / thrbp / thrnogate / official 全都链接失败。
// 上面那段注释说的 "A/B between the two archives" 因此一直做不成,而生产出货的正是
// generic ⇒ 09-09~09-14 的全部测量都在一个生产不出货的引擎档上。补齐兜底后,
// 台架可直接链**生产那份逐字节相同的** libxrslam_generic_4beb1a9.a,引擎一个字节不改。
//
// 缺席必须可观测,不能伪装成正常值(静默出口是本项目头号复发缺陷):
//  · 位姿:清零 ⇒ timestamp 0 ⇒ 调用点既有的 `pose.timestamp <= 0.0` 判据会返回
//    XRSLAM_BENCH_NONFINITE_OUTPUT,**失败关闭,不伪造位姿**。
//  · 计数器:**不填 0**。0 与"真的一次都没失败"无法区分,会把"读不到"读成"很健康"。
//    填 UINT64_MAX —— 单调递增的计数器不可能自然到达该值,产物里一眼可辨。
extern "C" __attribute__((weak)) void
XRSLAMGetPropagatedPose(XRSLAMPose *pose) {
  if (pose)
    *pose = XRSLAMPose{};
}
extern "C" __attribute__((weak)) void
XRSLAMGetInitCounters(unsigned long long *out, int count) {
  if (!out || count <= 0)
    return;
  for (int i = 0; i < count; ++i)
    out[i] = ~0ULL;
}

namespace {

constexpr double kSecondsPerNanosecond = 1e-9;
constexpr double kCoreMotionGravityScale = -9.80665;

enum class EventKind { Acceleration, Gyroscope, Image };

constexpr uint64_t kImageSlotCapacity = 1;
/// How many frames may be inside the engine at once.
///
/// With XRSLAM_ENABLE_THREADING the upstream `Worker::resume()` only notifies a
/// condition variable, so `run_one_frame` returns before the frame is tracked
/// and upstream's own queues (plain deques of whole images) have no bound. The
/// pose `get_result` hands back is `predict_pose()`, which follows the newest
/// input no matter how far the tracker has fallen behind, so it cannot serve as
/// a completion signal -- an earlier attempt to bound in flight frames by it
/// measured zero backlog while the engine was minutes behind. The backlog is
/// read from the engine instead, through the read-only accessor added by
/// xrslam_pending_worker_frames.patch. Two is the smallest bound that still
/// lets the feature tracker and the frontend work on different frames, which is
/// the whole point of turning threading on.
constexpr uint64_t kInFlightFrameCapacity = 2;
constexpr size_t kResultQueueCapacity = 16;

bool finite3(double x, double y, double z) {
  return std::isfinite(x) && std::isfinite(y) && std::isfinite(z);
}

bool pose_is_finite(const XRSLAMPose &pose) {
  if (!std::isfinite(pose.timestamp))
    return false;
  for (double value : pose.quaternion) {
    if (!std::isfinite(value))
      return false;
  }
  for (double value : pose.translation) {
    if (!std::isfinite(value))
      return false;
  }
  return true;
}

bool seconds_to_nanoseconds(double seconds, int64_t *out) {
  if (out == nullptr || !std::isfinite(seconds))
    return false;
  const long double nanoseconds =
      static_cast<long double>(seconds) * 1000000000.0L;
  if (nanoseconds <
          static_cast<long double>(std::numeric_limits<int64_t>::min()) ||
      nanoseconds >
          static_cast<long double>(std::numeric_limits<int64_t>::max())) {
    return false;
  }
  *out = static_cast<int64_t>(std::llround(nanoseconds));
  return true;
}

bool api_is_complete(const xrslam_bench_upstream_api *api) {
  return api != nullptr && api->create != nullptr &&
         api->push_sensor_data != nullptr && api->run_one_frame != nullptr &&
         api->get_result != nullptr && api->destroy != nullptr;
}

#if defined(PW_XRSLAM_CORE_LINKED) && PW_XRSLAM_CORE_LINKED
const xrslam_bench_upstream_api kProductionAPI = {
    XRSLAMCreate, XRSLAMPushSensorData, XRSLAMRunOneFrame, XRSLAMGetResult,
    XRSLAMDestroy};
#endif

std::mutex g_lifecycle_mutex;
struct xrslam_bench *g_active_bench = nullptr;

} // namespace

struct xrslam_bench {
  std::mutex mutex;
  xrslam_bench_upstream_api api{};
  void *upstream_config = nullptr;
  xrslam_bench_phase_t phase = XRSLAM_BENCH_PHASE_RUNNING;
  bool upstream_destroyed = false;
  bool has_last_event = false;
  bool has_last_accel = false;
  bool has_last_gyro = false;
  bool has_last_image = false;
  int64_t last_event_timestamp_ns = std::numeric_limits<int64_t>::min();
  int64_t last_accel_timestamp_ns = std::numeric_limits<int64_t>::min();
  int64_t last_gyro_timestamp_ns = std::numeric_limits<int64_t>::min();
  int64_t last_image_timestamp_ns = std::numeric_limits<int64_t>::min();
  uint32_t image_width = 0;
  uint32_t image_height = 0;
  std::vector<uint8_t> image_storage;
  bool has_pending_image = false;
  int64_t pending_image_timestamp_ns = 0;
  uint64_t image_slot_peak = 0;
  std::array<xrslam_bench_frame_result_t, kResultQueueCapacity> results{};
  size_t result_head = 0;
  size_t result_count = 0;
  uint64_t result_queue_peak = 0;
  uint64_t engine_backlog_peak = 0;
  xrslam_bench_counters_t counters{};
};

namespace {

void record_offered_locked(xrslam_bench *bench, EventKind kind) {
  ++bench->counters.events_offered;
  switch (kind) {
  case EventKind::Acceleration:
    ++bench->counters.accel_offered;
    break;
  case EventKind::Gyroscope:
    ++bench->counters.gyro_offered;
    break;
  case EventKind::Image:
    ++bench->counters.images_offered;
    break;
  }
}

void record_rejected_sealed_locked(xrslam_bench *bench, EventKind kind) {
  ++bench->counters.events_rejected_sealed;
  switch (kind) {
  case EventKind::Acceleration:
    ++bench->counters.accel_rejected_sealed;
    break;
  case EventKind::Gyroscope:
    ++bench->counters.gyro_rejected_sealed;
    break;
  case EventKind::Image:
    ++bench->counters.images_rejected_sealed;
    break;
  }
}

void record_rejected_timestamp_locked(xrslam_bench *bench, EventKind kind) {
  ++bench->counters.events_rejected_timestamp;
  switch (kind) {
  case EventKind::Acceleration:
    ++bench->counters.accel_rejected_timestamp;
    break;
  case EventKind::Gyroscope:
    ++bench->counters.gyro_rejected_timestamp;
    break;
  case EventKind::Image:
    ++bench->counters.images_rejected_timestamp;
    break;
  }
}

void record_rejected_queue_full_locked(xrslam_bench *bench, EventKind kind) {
  ++bench->counters.events_rejected_queue_full;
  switch (kind) {
  case EventKind::Acceleration:
    ++bench->counters.accel_rejected_queue_full;
    break;
  case EventKind::Gyroscope:
    ++bench->counters.gyro_rejected_queue_full;
    break;
  case EventKind::Image:
    ++bench->counters.images_rejected_queue_full;
    break;
  }
}

void release_singleton_ownership(xrslam_bench *bench) {
  std::lock_guard<std::mutex> lifecycle_lock(g_lifecycle_mutex);
  if (g_active_bench == bench)
    g_active_bench = nullptr;
}

xrslam_bench_status_t validate_timestamp_locked(xrslam_bench *bench,
                                                EventKind kind,
                                                int64_t timestamp_ns) {
  bool has_stream_timestamp = false;
  int64_t stream_timestamp = std::numeric_limits<int64_t>::min();
  switch (kind) {
  case EventKind::Acceleration:
    has_stream_timestamp = bench->has_last_accel;
    stream_timestamp = bench->last_accel_timestamp_ns;
    break;
  case EventKind::Gyroscope:
    has_stream_timestamp = bench->has_last_gyro;
    stream_timestamp = bench->last_gyro_timestamp_ns;
    break;
  case EventKind::Image:
    has_stream_timestamp = bench->has_last_image;
    stream_timestamp = bench->last_image_timestamp_ns;
    break;
  }
  if (timestamp_ns < 0 ||
      (has_stream_timestamp && timestamp_ns <= stream_timestamp)) {
    record_rejected_timestamp_locked(bench, kind);
    return XRSLAM_BENCH_TIMESTAMP_REGRESSION;
  }
  return XRSLAM_BENCH_OK;
}

void record_timestamp_locked(xrslam_bench *bench, EventKind kind,
                             int64_t timestamp_ns) {
  bench->has_last_event = true;
  bench->last_event_timestamp_ns = timestamp_ns;
  switch (kind) {
  case EventKind::Acceleration:
    bench->has_last_accel = true;
    bench->last_accel_timestamp_ns = timestamp_ns;
    ++bench->counters.accel_accepted;
    break;
  case EventKind::Gyroscope:
    bench->has_last_gyro = true;
    bench->last_gyro_timestamp_ns = timestamp_ns;
    ++bench->counters.gyro_accepted;
    break;
  case EventKind::Image:
    bench->has_last_image = true;
    bench->last_image_timestamp_ns = timestamp_ns;
    ++bench->counters.images_accepted;
    break;
  }
  ++bench->counters.events_accepted;
}

xrslam_bench_status_t enqueue_vector(xrslam_bench *bench, EventKind kind,
                                     int64_t timestamp_ns, double x, double y,
                                     double z) {
  if (bench == nullptr || !finite3(x, y, z)) {
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  }
  std::lock_guard<std::mutex> lock(bench->mutex);
  record_offered_locked(bench, kind);
  if (bench->phase != XRSLAM_BENCH_PHASE_RUNNING) {
    record_rejected_sealed_locked(bench, kind);
    return XRSLAM_BENCH_INPUT_SEALED;
  }
  /* The public contract requires push_image -> run_one_frame to be atomic on
     the caller's serial queue. Refuse interleaving instead of silently
     reordering an IMU callback ahead of an already accepted camera event. */
  if (bench->has_pending_image) {
    record_rejected_queue_full_locked(bench, kind);
    return XRSLAM_BENCH_QUEUE_FULL;
  }
  const xrslam_bench_status_t timestamp_status =
      validate_timestamp_locked(bench, kind, timestamp_ns);
  if (timestamp_status != XRSLAM_BENCH_OK)
    return timestamp_status;
  try {
    const double timestamp_seconds =
        static_cast<double>(timestamp_ns) * kSecondsPerNanosecond;
    if (kind == EventKind::Acceleration) {
      XRSLAMAcceleration acceleration{{x, y, z}, timestamp_seconds};
      bench->api.push_sensor_data(XRSLAM_SENSOR_ACCELERATION, &acceleration);
      ++bench->counters.accel_processed;
    } else if (kind == EventKind::Gyroscope) {
      XRSLAMGyroscope gyroscope{{x, y, z}, timestamp_seconds};
      bench->api.push_sensor_data(XRSLAM_SENSOR_GYROSCOPE, &gyroscope);
      ++bench->counters.gyro_processed;
    } else {
      return XRSLAM_BENCH_INTERNAL_ERROR;
    }
  } catch (...) {
    bench->phase = XRSLAM_BENCH_PHASE_FAILED;
    return XRSLAM_BENCH_INTERNAL_ERROR;
  }
  record_timestamp_locked(bench, kind, timestamp_ns);
  ++bench->counters.events_processed;
  return XRSLAM_BENCH_OK;
}

xrslam_bench_status_t run_next_frame_locked(xrslam_bench *bench) {
  if (!bench->has_pending_image)
    return XRSLAM_BENCH_NO_FRAME;
  if (bench->result_count == kResultQueueCapacity) {
    ++bench->counters.results_rejected_queue_full;
    return XRSLAM_BENCH_QUEUE_FULL;
  }

  try {
    XRSLAMImage image{};
    image.data = bench->image_storage.data();
    image.timeStamp =
        static_cast<double>(bench->pending_image_timestamp_ns) *
        kSecondsPerNanosecond;
    image.stride = static_cast<int>(bench->image_width);
    image.camera_id = 0;
    image.channel = 1;
    image.ext = nullptr;
    /* Temporary: a replay died inside the first frame with no way to tell
       which of push / run / get_result it died in. */
    const bool trace = bench->counters.frames_run < 3;
    if (trace) {
      fprintf(stderr, "[xrslam-trace] imu so far: accel=%llu gyro=%llu\n",
              (unsigned long long)bench->counters.accel_processed,
              (unsigned long long)bench->counters.gyro_processed);
      fflush(stderr);
    }
    if (trace) {
      fprintf(stderr, "[xrslam-trace] frame %llu push_image %ux%u stride=%d\n",
              (unsigned long long)bench->counters.frames_run,
              bench->image_width, bench->image_height, image.stride);
      fflush(stderr);
    }
    bench->api.push_sensor_data(XRSLAM_SENSOR_CAMERA, &image);
    if (trace) { fprintf(stderr, "[xrslam-trace] push_image returned\n"); fflush(stderr); }
    const int64_t input_timestamp_ns = bench->pending_image_timestamp_ns;
    bench->has_pending_image = false;
    ++bench->counters.events_processed;
    ++bench->counters.images_processed;

    if (trace) { fprintf(stderr, "[xrslam-trace] run_one_frame enter\n"); fflush(stderr); }
    bench->api.run_one_frame();
    if (trace) { fprintf(stderr, "[xrslam-trace] run_one_frame returned\n"); fflush(stderr); }
    ++bench->counters.frames_run;

    XRSLAMState state = XRSLAM_STATE_INITIALIZING;
    XRSLAMPose pose{};
    if (trace) { fprintf(stderr, "[xrslam-trace] get_result enter\n"); fflush(stderr); }
    bench->api.get_result(XRSLAM_RESULT_STATE, &state);
    bench->api.get_result(XRSLAM_RESULT_BODY_POSE, &pose);
    if (trace) {
      fprintf(stderr, "[xrslam-trace] get_result returned state=%d\n", (int)state);
      fflush(stderr);
    }

    int64_t pose_timestamp_ns = 0;
    {
      // Same predicate as before, but each cause is counted on its own; the
      // composite stays for the existing gate and receipts.
      const bool state_bad = state < XRSLAM_STATE_INITIALIZING ||
                             state > XRSLAM_STATE_TRACKING_FAIL;
      const bool pose_bad = !pose_is_finite(pose);
      const bool ts_bad =
          !seconds_to_nanoseconds(pose.timestamp, &pose_timestamp_ns);
      if (state_bad || pose_bad || ts_bad) {
        if (state_bad) ++bench->counters.result_state_out_of_range;
        if (pose_bad) ++bench->counters.result_pose_nonfinite;
        if (ts_bad) ++bench->counters.result_timestamp_unconvertible;
        ++bench->counters.nonfinite_results_rejected;
        return XRSLAM_BENCH_NONFINITE_OUTPUT;
      }
    }

    // A pose whose estimator has diverged is still finite and still reports
    // TRACKING_SUCCESS, so the verdict has to travel with the frame.
    const int divergence = XRSLAMGetDivergenceFlags();
    if (divergence != 0) {
      ++bench->counters.divergence_frames;
      bench->counters.divergence_flags_seen |= (uint64_t)divergence;
      const double sustained = XRSLAMGetDivergenceSustainedSeconds();
      if (sustained > bench->counters.divergence_longest_ms / 1000.0) {
        bench->counters.divergence_longest_ms = (uint64_t)(sustained * 1000.0);
      }
      // ORB-SLAM3's inertial time_recently_lost.
      if (sustained > 5.0)
        ++bench->counters.divergence_sustained_frames;
    }

    xrslam_bench_frame_result_t result{};
    result.divergence_flags = (int32_t)divergence;
    result.input_timestamp_ns = input_timestamp_ns;
    result.pose_timestamp_ns = pose_timestamp_ns;
    result.pose_timestamp_seconds = pose.timestamp;
    std::copy(std::begin(pose.quaternion), std::end(pose.quaternion),
              result.quaternion_xyzw);
    std::copy(std::begin(pose.translation), std::end(pose.translation),
              result.translation_xyz);
    result.state = static_cast<int32_t>(state);
    const size_t result_tail =
        (bench->result_head + bench->result_count) % kResultQueueCapacity;
    bench->results[result_tail] = result;
    ++bench->result_count;
    bench->result_queue_peak =
        std::max<uint64_t>(bench->result_queue_peak, bench->result_count);
    ++bench->counters.results_produced;
    return XRSLAM_BENCH_OK;
  } catch (...) {
    bench->phase = XRSLAM_BENCH_PHASE_FAILED;
    return XRSLAM_BENCH_INTERNAL_ERROR;
  }
}

xrslam_bench_status_t seal_locked(xrslam_bench *bench) {
  switch (bench->phase) {
  case XRSLAM_BENCH_PHASE_RUNNING:
    bench->phase = XRSLAM_BENCH_PHASE_SEALED;
    return XRSLAM_BENCH_OK;
  case XRSLAM_BENCH_PHASE_SEALED:
  case XRSLAM_BENCH_PHASE_DRAINED:
  case XRSLAM_BENCH_PHASE_STOPPED:
    return XRSLAM_BENCH_OK;
  case XRSLAM_BENCH_PHASE_FAILED:
    return XRSLAM_BENCH_INVALID_STATE;
  }
  return XRSLAM_BENCH_INTERNAL_ERROR;
}

xrslam_bench_status_t drain_locked(xrslam_bench *bench) {
  if (bench->phase == XRSLAM_BENCH_PHASE_STOPPED ||
      bench->phase == XRSLAM_BENCH_PHASE_DRAINED) {
    return XRSLAM_BENCH_OK;
  }
  if (bench->phase == XRSLAM_BENCH_PHASE_FAILED) {
    return XRSLAM_BENCH_INVALID_STATE;
  }
  const xrslam_bench_status_t seal_status = seal_locked(bench);
  if (seal_status != XRSLAM_BENCH_OK)
    return seal_status;

  while (bench->has_pending_image) {
    const xrslam_bench_status_t frame_status = run_next_frame_locked(bench);
    if (frame_status != XRSLAM_BENCH_OK)
      return frame_status;
  }
  bench->phase = XRSLAM_BENCH_PHASE_DRAINED;
  return XRSLAM_BENCH_OK;
}

xrslam_bench_status_t
create_with_api(const xrslam_bench_create_options_t *options,
                const xrslam_bench_upstream_api *api,
                xrslam_bench_t **out_bench) {
  if (out_bench == nullptr)
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  *out_bench = nullptr;
  if (options == nullptr ||
      options->struct_size != sizeof(xrslam_bench_create_options_t) ||
      options->slam_config_path == nullptr ||
      options->device_config_path == nullptr ||
      options->slam_config_path[0] == '\0' ||
      options->device_config_path[0] == '\0' || options->image_width == 0 ||
      options->image_height == 0 || !api_is_complete(api)) {
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  }

  std::lock_guard<std::mutex> lifecycle_lock(g_lifecycle_mutex);
  if (g_active_bench != nullptr)
    return XRSLAM_BENCH_INVALID_STATE;

  xrslam_bench *bench = new (std::nothrow) xrslam_bench();
  if (bench == nullptr)
    return XRSLAM_BENCH_INTERNAL_ERROR;
  bench->api = *api;
  bench->image_width = options->image_width;
  bench->image_height = options->image_height;
  try {
    const size_t image_size = static_cast<size_t>(bench->image_width) *
                              static_cast<size_t>(bench->image_height);
    if (image_size / bench->image_width != bench->image_height) {
      delete bench;
      return XRSLAM_BENCH_INVALID_ARGUMENT;
    }
    bench->image_storage.resize(image_size);
    /* Paths, not contents. Upstream decides this with a build flag:

         #if defined(XRSLAM_IOS)
             slam_config = YAML::Load(slam_config_filename);      // content
         #else
             slam_config = YAML::LoadFile(slam_config_filename);  // path
         #endif

       The official iOS sample passes contents because it is built with the
       macro. This bench links libxrslam_generic, built without it -- its own
       receipt records xrslam_ios: false -- so paths are what it wants. Passing
       contents here made create fail outright. */
    fprintf(stderr, "[xrslam-trace] create() slam=%s device=%s\n",
            options->slam_config_path, options->device_config_path);
    fflush(stderr);
    const int created = bench->api.create(
        options->slam_config_path, options->device_config_path, "",
        "xrslam-vio-bench", &bench->upstream_config);
    fprintf(stderr, "[xrslam-trace] create() -> %d config=%p\n",
            created, bench->upstream_config);
    fflush(stderr);
    if (created != 1 || bench->upstream_config == nullptr) {
      if (created == 1) {
        try {
          fprintf(stderr, "[xrslam-trace] destroy() called\n"); fflush(stderr);
        bench->api.destroy();
        } catch (...) {
        }
      }
      delete bench;
      return XRSLAM_BENCH_CREATE_FAILED;
    }
  } catch (...) {
    delete bench;
    return XRSLAM_BENCH_CREATE_FAILED;
  }

  g_active_bench = bench;
  *out_bench = bench;
  return XRSLAM_BENCH_OK;
}

} // namespace

extern "C" int xrslam_bench_backend_available(void) {
#if defined(PW_XRSLAM_CORE_LINKED) && PW_XRSLAM_CORE_LINKED
  return 1;
#else
  return 0;
#endif
}

extern "C" xrslam_bench_status_t
xrslam_bench_create(const xrslam_bench_create_options_t *options,
                    xrslam_bench_t **out_bench) {
#if defined(PW_XRSLAM_CORE_LINKED) && PW_XRSLAM_CORE_LINKED
  return create_with_api(options, &kProductionAPI, out_bench);
#else
  if (out_bench == nullptr)
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  *out_bench = nullptr;
  (void)options;
  return XRSLAM_BENCH_BACKEND_UNAVAILABLE;
#endif
}

xrslam_bench_status_t xrslam_bench_create_with_api_for_testing(
    const xrslam_bench_create_options_t *options,
    const xrslam_bench_upstream_api *api, xrslam_bench_t **out_bench) {
  return create_with_api(options, api, out_bench);
}

extern "C" xrslam_bench_status_t
xrslam_bench_push_accelerometer_g(xrslam_bench_t *bench, int64_t timestamp_ns,
                                  double x_g, double y_g, double z_g) {
  return enqueue_vector(bench, EventKind::Acceleration, timestamp_ns,
                        x_g * kCoreMotionGravityScale,
                        y_g * kCoreMotionGravityScale,
                        z_g * kCoreMotionGravityScale);
}

extern "C" xrslam_bench_status_t
xrslam_bench_push_acceleration_mps2(xrslam_bench_t *bench, int64_t timestamp_ns,
                                    double x, double y, double z) {
  return enqueue_vector(bench, EventKind::Acceleration, timestamp_ns, x, y, z);
}

extern "C" xrslam_bench_status_t
xrslam_bench_push_gyroscope(xrslam_bench_t *bench, int64_t timestamp_ns,
                            double x, double y, double z) {
  return enqueue_vector(bench, EventKind::Gyroscope, timestamp_ns, x, y, z);
}

extern "C" xrslam_bench_status_t
xrslam_bench_push_image(xrslam_bench_t *bench, int64_t timestamp_ns,
                        const xrslam_bench_image_t *image) {
  if (bench == nullptr || image == nullptr || image->gray_pixels == nullptr ||
      image->width != bench->image_width ||
      image->height != bench->image_height ||
      image->bytes_per_row < bench->image_width) {
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  }

  std::lock_guard<std::mutex> lock(bench->mutex);
  record_offered_locked(bench, EventKind::Image);
  if (bench->phase != XRSLAM_BENCH_PHASE_RUNNING) {
    record_rejected_sealed_locked(bench, EventKind::Image);
    return XRSLAM_BENCH_INPUT_SEALED;
  }
  if (bench->has_pending_image) {
    record_rejected_queue_full_locked(bench, EventKind::Image);
    return XRSLAM_BENCH_QUEUE_FULL;
  }
  const xrslam_bench_status_t timestamp_status =
      validate_timestamp_locked(bench, EventKind::Image, timestamp_ns);
  if (timestamp_status != XRSLAM_BENCH_OK)
    return timestamp_status;

  for (uint32_t row = 0; row < bench->image_height; ++row) {
    std::memcpy(bench->image_storage.data() +
                    static_cast<size_t>(row) * bench->image_width,
                image->gray_pixels +
                    static_cast<size_t>(row) * image->bytes_per_row,
                bench->image_width);
  }
  bench->pending_image_timestamp_ns = timestamp_ns;
  bench->has_pending_image = true;
  bench->image_slot_peak = 1;
  record_timestamp_locked(bench, EventKind::Image, timestamp_ns);
  bench->counters.image_bytes_copied +=
      static_cast<uint64_t>(bench->image_width) * bench->image_height;
  return XRSLAM_BENCH_OK;
}

extern "C" xrslam_bench_status_t
xrslam_bench_push_euroc_image_file(xrslam_bench_t *bench,
                                   int64_t timestamp_ns,
                                   const char *image_path) {
  if (bench == nullptr || image_path == nullptr || image_path[0] == '\0')
    return XRSLAM_BENCH_INVALID_ARGUMENT;

#if defined(PW_XRSLAM_CORE_LINKED) && PW_XRSLAM_CORE_LINKED
  try {
    cv::Mat img_distorted = cv::imread(image_path, cv::IMREAD_UNCHANGED);
    if (img_distorted.empty()) {
      std::lock_guard<std::mutex> lock(bench->mutex);
      ++bench->counters.replay_image_decode_failures;
      return XRSLAM_BENCH_INVALID_ARGUMENT;
    }
    {
      std::lock_guard<std::mutex> lock(bench->mutex);
      ++bench->counters.replay_images_decoded;
    }

    // Byte-for-byte parameter and float-matrix construction semantics from
    // pinned upstream 4beb1a9 EurocDatasetReader::read_image().
    cv::Mat distortion =
        (cv::Mat_<float>(4, 1) << -0.28340811f, 0.07395907f,
         0.00019359f, 1.76187114e-05f);
    cv::Mat intrinsic =
        (cv::Mat_<float>(3, 3) << 458.654f, 0.0f, 367.215f, 0.0f,
         457.296f, 248.375f, 0.0f, 0.0f, 1.0f);
    cv::Mat img;
    cv::undistort(img_distorted, img, intrinsic, distortion);
    if (img.channels() != 1)
      cv::cvtColor(img, img, cv::COLOR_BGR2GRAY);
    if (img.empty() || !img.isContinuous() || img.elemSize() != 1) {
      std::lock_guard<std::mutex> lock(bench->mutex);
      ++bench->counters.replay_image_preprocess_failures;
      return XRSLAM_BENCH_INTERNAL_ERROR;
    }

    xrslam_bench_image_t image{};
    image.gray_pixels = img.ptr<uint8_t>();
    image.width = static_cast<uint32_t>(img.cols);
    image.height = static_cast<uint32_t>(img.rows);
    image.bytes_per_row = static_cast<uint32_t>(img.step[0]);
    const xrslam_bench_status_t status =
        xrslam_bench_push_image(bench, timestamp_ns, &image);
    if (status == XRSLAM_BENCH_OK) {
      std::lock_guard<std::mutex> lock(bench->mutex);
      ++bench->counters.replay_images_undistorted;
    }
    return status;
  } catch (...) {
    std::lock_guard<std::mutex> lock(bench->mutex);
    ++bench->counters.replay_image_preprocess_failures;
    return XRSLAM_BENCH_INTERNAL_ERROR;
  }
#else
  (void)timestamp_ns;
  return XRSLAM_BENCH_BACKEND_UNAVAILABLE;
#endif
}

extern "C" xrslam_bench_status_t
xrslam_bench_run_one_frame(xrslam_bench_t *bench) {
  if (bench == nullptr)
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  std::lock_guard<std::mutex> lock(bench->mutex);
  if (bench->phase == XRSLAM_BENCH_PHASE_DRAINED ||
      bench->phase == XRSLAM_BENCH_PHASE_STOPPED ||
      bench->phase == XRSLAM_BENCH_PHASE_FAILED) {
    return XRSLAM_BENCH_INVALID_STATE;
  }
  return run_next_frame_locked(bench);
}

extern "C" xrslam_bench_status_t
xrslam_bench_poll_result(xrslam_bench_t *bench,
                         xrslam_bench_frame_result_t *out_result) {
  if (bench == nullptr || out_result == nullptr) {
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  }
  *out_result = {};
  std::lock_guard<std::mutex> lock(bench->mutex);
  if (bench->result_count == 0) {
    return bench->phase == XRSLAM_BENCH_PHASE_DRAINED ||
                   bench->phase == XRSLAM_BENCH_PHASE_STOPPED
               ? XRSLAM_BENCH_END_OF_STREAM
               : XRSLAM_BENCH_NO_OUTPUT;
  }
  *out_result = bench->results[bench->result_head];
  bench->result_head = (bench->result_head + 1) % kResultQueueCapacity;
  --bench->result_count;
  ++bench->counters.results_polled;
  return XRSLAM_BENCH_OK;
}

extern "C" xrslam_bench_status_t
xrslam_bench_query_pose(xrslam_bench_t *bench,
                        xrslam_bench_frame_result_t *out_result) {
  if (bench == nullptr || out_result == nullptr) {
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  }
  *out_result = {};
  std::lock_guard<std::mutex> lock(bench->mutex);
  if (bench->phase != XRSLAM_BENCH_PHASE_RUNNING) {
    return XRSLAM_BENCH_END_OF_STREAM;
  }
  if (bench->counters.frames_run == 0) {
    return XRSLAM_BENCH_NO_OUTPUT;
  }
  XRSLAMState state = XRSLAM_STATE_INITIALIZING;
  XRSLAMPose pose{};
  bench->api.get_result(XRSLAM_RESULT_STATE, &state);
  /* Not get_result(BODY_POSE): that one is written in track_camera and so advances once per image.
     XRSLAMGetPropagatedPose returns what track_gyroscope/track_accelerometer already computed for
     the newest IMU sample. */
  XRSLAMGetPropagatedPose(&pose);
  int64_t pose_timestamp_ns = 0;
  if (state < XRSLAM_STATE_INITIALIZING || state > XRSLAM_STATE_TRACKING_FAIL ||
      !pose_is_finite(pose) || pose.timestamp <= 0.0 ||
      !seconds_to_nanoseconds(pose.timestamp, &pose_timestamp_ns)) {
    return XRSLAM_BENCH_NONFINITE_OUTPUT;
  }
  /* No input_timestamp_ns: this pose belongs to no single image. The caller
     dates it by pose_timestamp_ns, which is the sensor time the propagation
     reached. */
  out_result->divergence_flags = (int32_t)XRSLAMGetDivergenceFlags();
  out_result->input_timestamp_ns = 0;
  out_result->pose_timestamp_ns = pose_timestamp_ns;
  out_result->pose_timestamp_seconds = pose.timestamp;
  for (int i = 0; i < 4; ++i)
    out_result->quaternion_xyzw[i] = pose.quaternion[i];
  for (int i = 0; i < 3; ++i)
    out_result->translation_xyz[i] = pose.translation[i];
  out_result->state = (int32_t)state;
  ++bench->counters.poses_queried;
  return XRSLAM_BENCH_OK;
}

extern "C" xrslam_bench_status_t
xrslam_bench_seal_inputs(xrslam_bench_t *bench) {
  if (bench == nullptr)
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  std::lock_guard<std::mutex> lock(bench->mutex);
  return seal_locked(bench);
}

extern "C" xrslam_bench_status_t xrslam_bench_drain(xrslam_bench_t *bench) {
  if (bench == nullptr)
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  std::lock_guard<std::mutex> lock(bench->mutex);
  return drain_locked(bench);
}

extern "C" xrslam_bench_status_t xrslam_bench_stop(xrslam_bench_t *bench) {
  if (bench == nullptr)
    return XRSLAM_BENCH_INVALID_ARGUMENT;

  xrslam_bench_status_t drain_status = XRSLAM_BENCH_OK;
  xrslam_bench_status_t destroy_status = XRSLAM_BENCH_OK;
  {
    std::lock_guard<std::mutex> lock(bench->mutex);
    if (bench->phase == XRSLAM_BENCH_PHASE_STOPPED) {
      return XRSLAM_BENCH_OK;
    }
    if (bench->phase != XRSLAM_BENCH_PHASE_FAILED) {
      drain_status = drain_locked(bench);
    } else {
      drain_status = XRSLAM_BENCH_INVALID_STATE;
    }
    if (!bench->upstream_destroyed) {
      try {
        fprintf(stderr, "[xrslam-trace] destroy() called\n"); fflush(stderr);
        bench->api.destroy();
        ++bench->counters.upstream_destroy_calls;
      } catch (...) {
        destroy_status = XRSLAM_BENCH_INTERNAL_ERROR;
      }
      bench->upstream_destroyed = true;
    }
    bench->phase = XRSLAM_BENCH_PHASE_STOPPED;
  }
  release_singleton_ownership(bench);
  if (drain_status != XRSLAM_BENCH_OK)
    return drain_status;
  return destroy_status;
}

extern "C" xrslam_bench_status_t
xrslam_bench_get_snapshot(xrslam_bench_t *bench,
                          xrslam_bench_snapshot_t *out_snapshot) {
  if (bench == nullptr || out_snapshot == nullptr) {
    return XRSLAM_BENCH_INVALID_ARGUMENT;
  }
  *out_snapshot = {};
  std::lock_guard<std::mutex> lock(bench->mutex);
  out_snapshot->phase = bench->phase;
  out_snapshot->last_event_timestamp_ns = bench->last_event_timestamp_ns;
  out_snapshot->last_accel_timestamp_ns = bench->last_accel_timestamp_ns;
  out_snapshot->last_gyro_timestamp_ns = bench->last_gyro_timestamp_ns;
  out_snapshot->last_image_timestamp_ns = bench->last_image_timestamp_ns;
  // The queue the feeder must respect is the engine's own backlog, not the
  // single handoff slot: with threading the slot empties immediately and the
  // frames accumulate inside upstream's workers.
  const uint64_t engine_backlog =
      static_cast<uint64_t>(XRSLAMGetPendingWorkerFrames());
  bench->engine_backlog_peak =
      std::max<uint64_t>(bench->engine_backlog_peak, engine_backlog);
  out_snapshot->engine_backlog_peak = bench->engine_backlog_peak;
  {
    unsigned long long ic[9] = {};
    XRSLAMGetInitCounters(ic, 9);
    bench->counters.init_too_few_frames = ic[0];
    bench->counters.init_attempts = ic[1];
    bench->counters.init_fail_matches = ic[2];
    bench->counters.init_fail_parallax = ic[3];
    bench->counters.init_fail_rotation = ic[4];
    bench->counters.init_fail_triangulation = ic[5];
    bench->counters.init_fail_imu = ic[6];
    bench->counters.init_success = ic[7];
    out_snapshot->init_too_few_frames = ic[0];
    out_snapshot->init_attempts = ic[1];
    out_snapshot->init_fail_matches = ic[2];
    out_snapshot->init_fail_parallax = ic[3];
    out_snapshot->init_fail_rotation = ic[4];
    out_snapshot->init_fail_triangulation = ic[5];
    out_snapshot->init_fail_imu = ic[6];
    out_snapshot->init_success = ic[7];
    out_snapshot->result_state_out_of_range =
        bench->counters.result_state_out_of_range;
    out_snapshot->result_pose_nonfinite = bench->counters.result_pose_nonfinite;
    out_snapshot->result_timestamp_unconvertible =
        bench->counters.result_timestamp_unconvertible;
    out_snapshot->init_mirror_us = ic[8];
  }
  out_snapshot->pending_event_count =
      engine_backlog + (bench->has_pending_image ? 1 : 0);
  out_snapshot->pending_result_count = bench->result_count;
  out_snapshot->event_queue_capacity = kInFlightFrameCapacity;
  XRSLAMGetIngestCounts(&out_snapshot->estimator_imu_ingested,
                        &out_snapshot->estimator_camera_ingested);
  out_snapshot->divergence_frames = bench->counters.divergence_frames;
  out_snapshot->divergence_flags_seen = bench->counters.divergence_flags_seen;
  out_snapshot->divergence_longest_ms = bench->counters.divergence_longest_ms;
  out_snapshot->divergence_sustained_frames =
      bench->counters.divergence_sustained_frames;
  out_snapshot->event_queue_peak =
      bench->image_slot_peak;
  out_snapshot->result_queue_capacity = kResultQueueCapacity;
  out_snapshot->result_queue_peak = bench->result_queue_peak;
  out_snapshot->counters = bench->counters;
  return XRSLAM_BENCH_OK;
}

extern "C" void xrslam_bench_destroy(xrslam_bench_t *bench) {
  if (bench == nullptr)
    return;
  (void)xrslam_bench_stop(bench);
  delete bench;
}

extern "C" const char *xrslam_bench_status_name(xrslam_bench_status_t status) {
  switch (status) {
  case XRSLAM_BENCH_OK:
    return "ok";
  case XRSLAM_BENCH_INVALID_ARGUMENT:
    return "invalid_argument";
  case XRSLAM_BENCH_BACKEND_UNAVAILABLE:
    return "backend_unavailable";
  case XRSLAM_BENCH_CREATE_FAILED:
    return "create_failed";
  case XRSLAM_BENCH_INVALID_STATE:
    return "invalid_state";
  case XRSLAM_BENCH_TIMESTAMP_REGRESSION:
    return "timestamp_regression";
  case XRSLAM_BENCH_INPUT_SEALED:
    return "input_sealed";
  case XRSLAM_BENCH_NO_FRAME:
    return "no_frame";
  case XRSLAM_BENCH_NO_OUTPUT:
    return "no_output";
  case XRSLAM_BENCH_END_OF_STREAM:
    return "end_of_stream";
  case XRSLAM_BENCH_NONFINITE_OUTPUT:
    return "nonfinite_output";
  case XRSLAM_BENCH_INTERNAL_ERROR:
    return "internal_error";
  case XRSLAM_BENCH_QUEUE_FULL:
    return "queue_full";
  }
  return "unknown";
}
