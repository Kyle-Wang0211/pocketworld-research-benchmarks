#if defined(PW_XRSLAM_STANDALONE_TESTS) && PW_XRSLAM_STANDALONE_TESTS

#include "../../XRSLAMBackend/Native/XRSLAMBenchTesting.hpp"

#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

namespace {

enum class Call { Accel, Gyro, Image, Run, State, Pose, Destroy };

struct FakeCore {
  bool create_success = true;
  bool nonfinite_pose = false;
  uint32_t expected_image_width = 640;
  uint32_t expected_image_height = 480;
  std::vector<Call> calls;
  std::vector<double> accel;
  std::vector<double> gyro;
  std::vector<double> timestamps;
  std::vector<uint8_t> image;
  int destroy_count = 0;
};

FakeCore *g_fake = nullptr;

int fake_create(const char *slam, const char *device, const char *,
                const char *, void **config) {
  assert(g_fake != nullptr);
  assert(std::strcmp(slam, "/config/slam.yaml") == 0);
  assert(std::strcmp(device, "/config/device.yaml") == 0);
  if (!g_fake->create_success)
    return 0;
  *config = g_fake;
  return 1;
}

void fake_push(XRSLAMSensorType type, void *data) {
  assert(g_fake != nullptr);
  if (type == XRSLAM_SENSOR_ACCELERATION) {
    const auto *sample = static_cast<XRSLAMAcceleration *>(data);
    g_fake->calls.push_back(Call::Accel);
    g_fake->accel.assign(sample->data, sample->data + 3);
    g_fake->timestamps.push_back(sample->timestamp);
  } else if (type == XRSLAM_SENSOR_GYROSCOPE) {
    const auto *sample = static_cast<XRSLAMGyroscope *>(data);
    g_fake->calls.push_back(Call::Gyro);
    g_fake->gyro.assign(sample->data, sample->data + 3);
    g_fake->timestamps.push_back(sample->timestamp);
  } else if (type == XRSLAM_SENSOR_CAMERA) {
    const auto *sample = static_cast<XRSLAMImage *>(data);
    g_fake->calls.push_back(Call::Image);
    assert(sample->stride == static_cast<int>(g_fake->expected_image_width));
    assert(sample->channel == 1);
    g_fake->timestamps.push_back(sample->timeStamp);
    g_fake->image.assign(
        sample->data,
        sample->data + g_fake->expected_image_width * g_fake->expected_image_height);
  } else {
    assert(false);
  }
}

void fake_run() { g_fake->calls.push_back(Call::Run); }

void fake_get(XRSLAMResultType type, void *result) {
  if (type == XRSLAM_RESULT_STATE) {
    g_fake->calls.push_back(Call::State);
    *static_cast<XRSLAMState *>(result) = XRSLAM_STATE_TRACKING_SUCCESS;
  } else if (type == XRSLAM_RESULT_BODY_POSE) {
    g_fake->calls.push_back(Call::Pose);
    auto *pose = static_cast<XRSLAMPose *>(result);
    pose->timestamp = 2e-8;
    pose->quaternion[0] =
        g_fake->nonfinite_pose ? std::numeric_limits<double>::quiet_NaN() : 0.0;
    pose->quaternion[1] = 0.0;
    pose->quaternion[2] = 0.0;
    pose->quaternion[3] = 1.0;
    pose->translation[0] = 1.0;
    pose->translation[1] = 2.0;
    pose->translation[2] = 3.0;
  } else {
    assert(false);
  }
}

void fake_destroy() {
  g_fake->calls.push_back(Call::Destroy);
  ++g_fake->destroy_count;
}

xrslam_bench_upstream_api fake_api() {
  return {fake_create, fake_push, fake_run, fake_get, fake_destroy};
}

xrslam_bench_create_options_t options(uint32_t width = 640,
                                      uint32_t height = 480) {
  xrslam_bench_create_options_t value{};
  value.struct_size = sizeof(value);
  value.slam_config_path = "/config/slam.yaml";
  value.device_config_path = "/config/device.yaml";
  value.image_width = width;
  value.image_height = height;
  return value;
}

xrslam_bench_t *create(FakeCore &fake, uint32_t width = 640,
                       uint32_t height = 480) {
  g_fake = &fake;
  fake.expected_image_width = width;
  fake.expected_image_height = height;
  auto api = fake_api();
  xrslam_bench_t *bench = nullptr;
  auto opts = options(width, height);
  assert(xrslam_bench_create_with_api_for_testing(&opts, &api, &bench) ==
         XRSLAM_BENCH_OK);
  assert(bench != nullptr);
  return bench;
}

void test_create_failure_leaves_null() {
  FakeCore fake;
  fake.create_success = false;
  g_fake = &fake;
  auto api = fake_api();
  auto opts = options();
  xrslam_bench_t *bench = reinterpret_cast<xrslam_bench_t *>(0x1);
  assert(xrslam_bench_create_with_api_for_testing(&opts, &api, &bench) ==
         XRSLAM_BENCH_CREATE_FAILED);
  assert(bench == nullptr);
}

void test_invalid_lifecycle_and_geometry_fail_closed() {
  xrslam_bench_frame_result_t result{};
  xrslam_bench_snapshot_t snapshot{};
  assert(xrslam_bench_push_gyroscope(nullptr, 1, 1, 2, 3) ==
         XRSLAM_BENCH_INVALID_ARGUMENT);
  assert(xrslam_bench_push_euroc_image_file(nullptr, 1, "/tmp/frame.png") ==
         XRSLAM_BENCH_INVALID_ARGUMENT);
  assert(xrslam_bench_run_one_frame(nullptr) == XRSLAM_BENCH_INVALID_ARGUMENT);
  assert(xrslam_bench_poll_result(nullptr, &result) ==
         XRSLAM_BENCH_INVALID_ARGUMENT);
  assert(xrslam_bench_get_snapshot(nullptr, &snapshot) ==
         XRSLAM_BENCH_INVALID_ARGUMENT);
  assert(xrslam_bench_seal_inputs(nullptr) == XRSLAM_BENCH_INVALID_ARGUMENT);
  assert(xrslam_bench_drain(nullptr) == XRSLAM_BENCH_INVALID_ARGUMENT);
  assert(xrslam_bench_stop(nullptr) == XRSLAM_BENCH_INVALID_ARGUMENT);
  xrslam_bench_destroy(nullptr);

  FakeCore fake;
  xrslam_bench_t *bench = create(fake);
  assert(xrslam_bench_push_euroc_image_file(bench, 1, nullptr) ==
         XRSLAM_BENCH_INVALID_ARGUMENT);
#if !defined(PW_XRSLAM_CORE_LINKED) || !PW_XRSLAM_CORE_LINKED
  assert(xrslam_bench_push_euroc_image_file(bench, 1, "/tmp/frame.png") ==
         XRSLAM_BENCH_BACKEND_UNAVAILABLE);
#endif
  std::vector<uint8_t> pixels(640 * 480);
  xrslam_bench_image_t bad_width{pixels.data(), 639, 480, 640};
  assert(xrslam_bench_push_image(bench, 1, &bad_width) ==
         XRSLAM_BENCH_INVALID_ARGUMENT);
  assert(xrslam_bench_push_acceleration_mps2(
             bench, 1, std::numeric_limits<double>::infinity(), 0, 0) ==
         XRSLAM_BENCH_INVALID_ARGUMENT);
  assert(xrslam_bench_run_one_frame(bench) == XRSLAM_BENCH_NO_FRAME);
  assert(xrslam_bench_stop(bench) == XRSLAM_BENCH_OK);
  xrslam_bench_destroy(bench);
  g_fake = nullptr;
}

void test_order_conversion_pose_and_lossless_stop() {
  FakeCore fake;
  xrslam_bench_t *bench = create(fake);

  assert(xrslam_bench_push_accelerometer_g(bench, 10, 1.0, -2.0, 0.5) ==
         XRSLAM_BENCH_OK);
  assert(xrslam_bench_push_gyroscope(bench, 10, 0.1, 0.2, 0.3) ==
         XRSLAM_BENCH_OK);

  std::vector<uint8_t> padded(672 * 480, 0xEE);
  for (int row = 0; row < 480; ++row) {
    std::memset(padded.data() + row * 672, row & 0xFF, 640);
  }
  xrslam_bench_image_t image{padded.data(), 640, 480, 672};
  assert(xrslam_bench_push_image(bench, 20, &image) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_run_one_frame(bench) == XRSLAM_BENCH_OK);

  const std::vector<Call> prefix = {Call::Accel, Call::Gyro,  Call::Image,
                                    Call::Run,   Call::State, Call::Pose};
  assert(fake.calls == prefix);
  assert(std::abs(fake.accel[0] - -9.80665) < 1e-12);
  assert(std::abs(fake.accel[1] - 19.61330) < 1e-12);
  assert(std::abs(fake.accel[2] - -4.903325) < 1e-12);
  assert(fake.gyro == std::vector<double>({0.1, 0.2, 0.3}));
  assert(fake.timestamps == std::vector<double>({1e-8, 1e-8, 2e-8}));
  assert(fake.image.size() == 640 * 480);
  assert(fake.image[0] == 0);
  assert(fake.image[640] == 1);

  xrslam_bench_frame_result_t result{};
  assert(xrslam_bench_poll_result(bench, &result) == XRSLAM_BENCH_OK);
  assert(result.input_timestamp_ns == 20);
  assert(result.pose_timestamp_ns == 20);
  assert(result.state == XRSLAM_STATE_TRACKING_SUCCESS);
  for (double value : result.quaternion_xyzw)
    assert(std::isfinite(value));
  for (double value : result.translation_xyz)
    assert(std::isfinite(value));

  /* Official transport validates monotonicity per stream. A later callback
     from another sensor may carry an older hardware timestamp and must retain
     its FIFO callback position instead of being dropped by an invented global
     clock gate. */
  assert(xrslam_bench_push_acceleration_mps2(bench, 30, 4, 5, 6) ==
         XRSLAM_BENCH_OK);
  assert(xrslam_bench_push_gyroscope(bench, 15, 1, 2, 3) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_push_gyroscope(bench, 15, 1, 2, 3) ==
         XRSLAM_BENCH_TIMESTAMP_REGRESSION);

  assert(xrslam_bench_stop(bench) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_stop(bench) == XRSLAM_BENCH_OK);
  assert(fake.destroy_count == 1);
  assert(fake.calls[fake.calls.size() - 2] == Call::Gyro);
  assert(fake.calls.back() == Call::Destroy);

  xrslam_bench_snapshot_t snapshot{};
  assert(xrslam_bench_get_snapshot(bench, &snapshot) == XRSLAM_BENCH_OK);
  assert(snapshot.phase == XRSLAM_BENCH_PHASE_STOPPED);
  assert(snapshot.pending_event_count == 0);
  assert(snapshot.counters.events_accepted ==
         snapshot.counters.events_processed);
  assert(snapshot.counters.accel_accepted == snapshot.counters.accel_processed);
  assert(snapshot.counters.gyro_accepted == snapshot.counters.gyro_processed);
  assert(snapshot.counters.images_accepted ==
         snapshot.counters.images_processed);
  assert(snapshot.counters.frames_run == snapshot.counters.results_produced);
  assert(snapshot.counters.events_rejected_timestamp == 1);
  assert(snapshot.counters.accel_offered == 2);
  assert(snapshot.counters.gyro_offered == 3);
  assert(snapshot.counters.images_offered == 1);
  assert(snapshot.counters.gyro_rejected_timestamp == 1);
  assert(snapshot.counters.accel_rejected_timestamp == 0);
  assert(snapshot.counters.images_rejected_timestamp == 0);
  assert(snapshot.counters.upstream_destroy_calls == 1);
  assert(xrslam_bench_push_gyroscope(bench, 40, 1, 2, 3) ==
         XRSLAM_BENCH_INPUT_SEALED);
  assert(xrslam_bench_poll_result(bench, &result) ==
         XRSLAM_BENCH_END_OF_STREAM);

  xrslam_bench_destroy(bench);
  g_fake = nullptr;
}

void test_drain_runs_all_queued_images_without_drops() {
  FakeCore fake;
  xrslam_bench_t *bench = create(fake);
  std::vector<uint8_t> pixels(640 * 480, 7);
  xrslam_bench_image_t image{pixels.data(), 640, 480, 640};

  assert(xrslam_bench_push_acceleration_mps2(bench, 1, 1, 2, 3) ==
         XRSLAM_BENCH_OK);
  assert(xrslam_bench_push_image(bench, 2, &image) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_push_image(bench, 4, &image) == XRSLAM_BENCH_QUEUE_FULL);

  xrslam_bench_snapshot_t before_run{};
  assert(xrslam_bench_get_snapshot(bench, &before_run) == XRSLAM_BENCH_OK);
  assert(before_run.pending_event_count == 1);
  assert(before_run.event_queue_capacity == 1);
  assert(before_run.event_queue_peak == 1);
  assert(before_run.result_queue_capacity == 16);
  assert(before_run.counters.images_rejected_queue_full == 1);

  assert(xrslam_bench_run_one_frame(bench) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_push_gyroscope(bench, 3, 4, 5, 6) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_push_image(bench, 4, &image) == XRSLAM_BENCH_OK);

  assert(xrslam_bench_seal_inputs(bench) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_drain(bench) == XRSLAM_BENCH_OK);

  xrslam_bench_snapshot_t snapshot{};
  assert(xrslam_bench_get_snapshot(bench, &snapshot) == XRSLAM_BENCH_OK);
  assert(snapshot.phase == XRSLAM_BENCH_PHASE_DRAINED);
  assert(snapshot.counters.events_accepted == 4);
  assert(snapshot.counters.events_processed == 4);
  assert(snapshot.counters.frames_run == 2);
  assert(snapshot.pending_result_count == 2);

  assert(xrslam_bench_stop(bench) == XRSLAM_BENCH_OK);
  xrslam_bench_frame_result_t result{};
  assert(xrslam_bench_poll_result(bench, &result) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_poll_result(bench, &result) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_poll_result(bench, &result) ==
         XRSLAM_BENCH_END_OF_STREAM);
  xrslam_bench_destroy(bench);
  g_fake = nullptr;
}

void test_replay_geometry_752x480_uses_preallocated_slot() {
  FakeCore fake;
  xrslam_bench_t *bench = create(fake, 752, 480);
  std::vector<uint8_t> padded(768 * 480, 0xEE);
  for (int row = 0; row < 480; ++row) {
    std::memset(padded.data() + row * 768, row & 0xFF, 752);
  }
  xrslam_bench_image_t image{padded.data(), 752, 480, 768};
  assert(xrslam_bench_push_image(bench, 10, &image) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_run_one_frame(bench) == XRSLAM_BENCH_OK);
  assert(fake.image.size() == 752 * 480);
  assert(fake.image[752] == 1);
  assert(xrslam_bench_stop(bench) == XRSLAM_BENCH_OK);
  xrslam_bench_destroy(bench);
  g_fake = nullptr;
}

void test_nonfinite_upstream_pose_is_counted_and_never_published() {
  FakeCore fake;
  fake.nonfinite_pose = true;
  xrslam_bench_t *bench = create(fake);
  std::vector<uint8_t> pixels(640 * 480);
  xrslam_bench_image_t image{pixels.data(), 640, 480, 640};
  assert(xrslam_bench_push_image(bench, 1, &image) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_run_one_frame(bench) == XRSLAM_BENCH_NONFINITE_OUTPUT);

  xrslam_bench_frame_result_t result{};
  assert(xrslam_bench_poll_result(bench, &result) == XRSLAM_BENCH_NO_OUTPUT);
  xrslam_bench_snapshot_t snapshot{};
  assert(xrslam_bench_get_snapshot(bench, &snapshot) == XRSLAM_BENCH_OK);
  assert(snapshot.phase == XRSLAM_BENCH_PHASE_RUNNING);
  assert(snapshot.counters.nonfinite_results_rejected == 1);
  assert(snapshot.counters.results_produced == 0);
  assert(snapshot.counters.images_accepted ==
         snapshot.counters.images_processed);
  /* A bad output is counted and withheld, but does not prevent the official
     core from draining later accepted input before Destroy. */
  assert(xrslam_bench_push_gyroscope(bench, 2, 1, 2, 3) == XRSLAM_BENCH_OK);
  assert(xrslam_bench_stop(bench) == XRSLAM_BENCH_OK);
  assert(fake.destroy_count == 1);
  assert(xrslam_bench_get_snapshot(bench, &snapshot) == XRSLAM_BENCH_OK);
  assert(snapshot.counters.events_accepted ==
         snapshot.counters.events_processed);
  xrslam_bench_destroy(bench);
  g_fake = nullptr;
}

} // namespace

int main() {
  test_create_failure_leaves_null();
  test_invalid_lifecycle_and_geometry_fail_closed();
  test_order_conversion_pose_and_lossless_stop();
  test_drain_runs_all_queued_images_without_drops();
  test_replay_geometry_752x480_uses_preallocated_slot();
  test_nonfinite_upstream_pose_is_counted_and_never_published();
  for (int raw = XRSLAM_BENCH_OK; raw <= XRSLAM_BENCH_QUEUE_FULL; ++raw) {
    assert(std::strcmp(xrslam_bench_status_name(
                           static_cast<xrslam_bench_status_t>(raw)),
                       "unknown") != 0);
  }
  return 0;
}

#endif // PW_XRSLAM_STANDALONE_TESTS
