// Minimal dumping fake of the XRSLAM C ABI for a cross-binary comparison.
#include "XRSLAM.h"
#include <cstdio>
#include <cstring>
#include <cstdint>
extern "C" const unsigned char *g_expected_pixels;
const unsigned char *g_expected_pixels = nullptr;
static_assert(sizeof(XRSLAMImage) == 40, "40");
extern "C" int XRSLAMCreate(const char *, const char *, const char *, const char *, void **) { std::printf("CALL create\n"); return 1; }
extern "C" void XRSLAMDestroy() { std::printf("CALL destroy\n"); }
extern "C" void XRSLAMRunOneFrame() { std::printf("CALL run\n"); }
extern "C" void XRSLAMPushSensorData(XRSLAMSensorType type, void *data) {
  if (type == XRSLAM_SENSOR_CAMERA) {
    unsigned char b[40];
    std::memcpy(b, data, 40);
    const XRSLAMImage *im = static_cast<const XRSLAMImage *>(data);
    const bool ptr_ok = reinterpret_cast<const unsigned char *>(im->data) == g_expected_pixels;
    std::printf("CALL push_camera data_ptr_matches=%d bytes[8..40)=", ptr_ok ? 1 : 0);
    for (int i = 8; i < 40; ++i) std::printf("%02x", b[i]);
    std::printf("\n");
  } else {
    std::printf("CALL push_sensor type=%d\n", (int)type);
  }
}
extern "C" void XRSLAMGetResult(XRSLAMResultType type, void *result) {
  std::printf("CALL get_result type=%d\n", (int)type);
  if (type == XRSLAM_RESULT_STATE) *static_cast<XRSLAMState *>(result) = XRSLAM_STATE_TRACKING_SUCCESS;
  else if (type == XRSLAM_RESULT_CAMERA_POSE) { XRSLAMPose p{}; p.quaternion[3] = 1.0; *static_cast<XRSLAMPose *>(result) = p; }
}
