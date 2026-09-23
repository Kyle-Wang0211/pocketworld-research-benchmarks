#include "PwXrslamTransportCore.h"
#include <cstdio>
#include <cstdint>
extern "C" const unsigned char *g_expected_pixels;
int main() {
  static uint8_t pixels[1920 * 4];
  g_expected_pixels = pixels;
  std::printf("create rc=%d\n", PWXrslamTransportCreateWithCameraTimeOffset("slam", "device", 0.0083));
  const int32_t strides[] = {7680, 640, 1920};
  const int32_t channels[] = {4, 1, 4};
  double t = 100.0;
  for (int i = 0; i < 6; ++i) {
    int32_t state = -1; PWXrslamRawPose pose{};
    int32_t rc;
#ifdef PW_NEW_API_NULL_K
    rc = PWXrslamTransportPushCameraAndRunRawWithIntrinsics(pixels, t, strides[i % 3], 0, channels[i % 3], nullptr, &state, &pose);
#else
    rc = PWXrslamTransportPushCameraAndRunRaw(pixels, t, strides[i % 3], 0, channels[i % 3], &state, &pose);
#endif
    std::printf("push rc=%d state=%d\n", rc, state);
    t += 1.0 / 30.0;
  }
  PWXrslamTransportDestroyWithReceipt(nullptr);
  return 0;
}
