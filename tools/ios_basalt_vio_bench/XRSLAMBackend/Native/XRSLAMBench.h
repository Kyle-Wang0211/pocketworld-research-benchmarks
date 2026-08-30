#ifndef XRSLAM_VIO_BENCH_NATIVE_H
#define XRSLAM_VIO_BENCH_NATIVE_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Stable C boundary around the frozen OpenXRLab XRSLAM generic C++ core at
 * 4beb1a942f33da9afbfae2d70e2c641cfc2bb675. This adapter does not use ARKit,
 * RealityKit, XRSLAM_iOS, or any alternate/synthetic estimator.
 *
 * Calls which submit sensors and advance frames must be serialized by the
 * caller. IMU events are forwarded synchronously in accepted callback order,
 * matching the official iOS sample. One create-time preallocated grayscale
 * slot holds the image only between push_image and run_one_frame; it cannot
 * grow. Monotonicity is checked per sensor stream. The only timestamp
 * conversion is ns -> seconds at the exact upstream C ABI boundary; no
 * camera/IMU offset is applied here.
 */
typedef struct xrslam_bench xrslam_bench_t;

typedef enum xrslam_bench_status {
  XRSLAM_BENCH_OK = 0,
  XRSLAM_BENCH_INVALID_ARGUMENT = 1,
  XRSLAM_BENCH_BACKEND_UNAVAILABLE = 2,
  XRSLAM_BENCH_CREATE_FAILED = 3,
  XRSLAM_BENCH_INVALID_STATE = 4,
  XRSLAM_BENCH_TIMESTAMP_REGRESSION = 5,
  XRSLAM_BENCH_INPUT_SEALED = 6,
  XRSLAM_BENCH_NO_FRAME = 7,
  XRSLAM_BENCH_NO_OUTPUT = 8,
  XRSLAM_BENCH_END_OF_STREAM = 9,
  XRSLAM_BENCH_NONFINITE_OUTPUT = 10,
  XRSLAM_BENCH_INTERNAL_ERROR = 11,
  XRSLAM_BENCH_QUEUE_FULL = 12
} xrslam_bench_status_t;

typedef enum xrslam_bench_phase {
  XRSLAM_BENCH_PHASE_RUNNING = 0,
  XRSLAM_BENCH_PHASE_SEALED = 1,
  XRSLAM_BENCH_PHASE_DRAINED = 2,
  XRSLAM_BENCH_PHASE_STOPPED = 3,
  XRSLAM_BENCH_PHASE_FAILED = 4
} xrslam_bench_phase_t;

typedef struct xrslam_bench_create_options {
  size_t struct_size;
  /* Filesystem paths. The frozen generic build has XRSLAM_IOS=false, so its
     official YamlConfig constructor uses YAML::LoadFile for both inputs. */
  const char *slam_config_path;
  const char *device_config_path;
  uint32_t image_width;
  uint32_t image_height;
} xrslam_bench_create_options_t;

typedef struct xrslam_bench_image {
  const uint8_t *gray_pixels;
  uint32_t width;
  uint32_t height;
  uint32_t bytes_per_row;
} xrslam_bench_image_t;

typedef struct xrslam_bench_frame_result {
  int64_t input_timestamp_ns;
  int64_t pose_timestamp_ns;
  double pose_timestamp_seconds;
  /* Exact official BODY_POSE fields: quaternion is x,y,z,w. */
  double quaternion_xyzw[4];
  double translation_xyz[3];
  int32_t state;
} xrslam_bench_frame_result_t;

typedef struct xrslam_bench_counters {
  uint64_t events_offered;
  uint64_t events_accepted;
  uint64_t events_processed;
  uint64_t events_rejected_timestamp;
  uint64_t events_rejected_sealed;
  uint64_t events_rejected_queue_full;
  uint64_t accel_offered;
  uint64_t accel_accepted;
  uint64_t accel_processed;
  uint64_t accel_rejected_timestamp;
  uint64_t accel_rejected_sealed;
  uint64_t accel_rejected_queue_full;
  uint64_t gyro_offered;
  uint64_t gyro_accepted;
  uint64_t gyro_processed;
  uint64_t gyro_rejected_timestamp;
  uint64_t gyro_rejected_sealed;
  uint64_t gyro_rejected_queue_full;
  uint64_t images_offered;
  uint64_t images_accepted;
  uint64_t images_processed;
  uint64_t images_rejected_timestamp;
  uint64_t images_rejected_sealed;
  uint64_t images_rejected_queue_full;
  uint64_t image_bytes_copied;
  uint64_t replay_images_decoded;
  uint64_t replay_images_undistorted;
  uint64_t replay_image_decode_failures;
  uint64_t replay_image_preprocess_failures;
  uint64_t frames_run;
  uint64_t results_produced;
  uint64_t results_polled;
  uint64_t results_rejected_queue_full;
  uint64_t nonfinite_results_rejected;
  uint64_t upstream_destroy_calls;
} xrslam_bench_counters_t;

typedef struct xrslam_bench_snapshot {
  xrslam_bench_phase_t phase;
  int64_t last_event_timestamp_ns;
  int64_t last_accel_timestamp_ns;
  int64_t last_gyro_timestamp_ns;
  int64_t last_image_timestamp_ns;
  uint64_t pending_event_count;
  uint64_t pending_result_count;
  uint64_t event_queue_capacity;
  uint64_t event_queue_peak;
  uint64_t result_queue_capacity;
  uint64_t result_queue_peak;
  xrslam_bench_counters_t counters;
} xrslam_bench_snapshot_t;

int xrslam_bench_backend_available(void);

xrslam_bench_status_t
xrslam_bench_create(const xrslam_bench_create_options_t *options,
                    xrslam_bench_t **out_bench);

/* Live Core Motion acceleration in G. The adapter explicitly multiplies each
   axis by the pinned upstream factor -9.80665 before calling XRSLAM. */
xrslam_bench_status_t xrslam_bench_push_accelerometer_g(xrslam_bench_t *bench,
                                                        int64_t timestamp_ns,
                                                        double x_g, double y_g,
                                                        double z_g);

/* EuRoC replay acceleration is already in m/s^2 and passes through unchanged.
 */
xrslam_bench_status_t xrslam_bench_push_acceleration_mps2(xrslam_bench_t *bench,
                                                          int64_t timestamp_ns,
                                                          double x, double y,
                                                          double z);

/* Gyroscope radians/second pass through unchanged for live and replay. */
xrslam_bench_status_t xrslam_bench_push_gyroscope(xrslam_bench_t *bench,
                                                  int64_t timestamp_ns,
                                                  double x, double y, double z);

/* Only the create-time configured 8-bit grayscale geometry is accepted.
   Pixels are copied into the single preallocated slot before this returns.
   The caller must immediately call run_one_frame before another sensor push. */
xrslam_bench_status_t
xrslam_bench_push_image(xrslam_bench_t *bench, int64_t timestamp_ns,
                        const xrslam_bench_image_t *image);

/* Exact pinned official EuRoC PC-reader image path. OpenCV 4.0.1 decodes the
   source PNG with IMREAD_UNCHANGED, applies cv::undistort using the frozen
   MH_01 cam0 float K/D values, and converts to gray only if still multichannel.
   Live iPhone frames must never enter this function. */
xrslam_bench_status_t
xrslam_bench_push_euroc_image_file(xrslam_bench_t *bench,
                                   int64_t timestamp_ns,
                                   const char *image_path);

/* Advances the frozen core through the pending image, then executes the
   official PC-evaluation XRSLAMRunOneFrame/GetResult(BODY_POSE,STATE)
   sequence. BODY_POSE matches Basalt's IMU state and EuRoC ground truth. */
xrslam_bench_status_t xrslam_bench_run_one_frame(xrslam_bench_t *bench);

xrslam_bench_status_t
xrslam_bench_poll_result(xrslam_bench_t *bench,
                         xrslam_bench_frame_result_t *out_result);

xrslam_bench_status_t xrslam_bench_seal_inputs(xrslam_bench_t *bench);
xrslam_bench_status_t xrslam_bench_drain(xrslam_bench_t *bench);

/* Idempotent official shutdown order: seal ingress, run the accepted pending
   image if present, then call XRSLAMDestroy exactly once. */
xrslam_bench_status_t xrslam_bench_stop(xrslam_bench_t *bench);

xrslam_bench_status_t
xrslam_bench_get_snapshot(xrslam_bench_t *bench,
                          xrslam_bench_snapshot_t *out_snapshot);

/* Safe on null. A live handle follows the same seal/drain/stop path first. */
void xrslam_bench_destroy(xrslam_bench_t *bench);

const char *xrslam_bench_status_name(xrslam_bench_status_t status);

#ifdef __cplusplus
}
#endif

#endif
