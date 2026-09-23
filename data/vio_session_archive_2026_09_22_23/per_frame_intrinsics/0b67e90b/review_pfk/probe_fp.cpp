#include <cstdio>
#include <array>
#include "fake_xrslam.h"
#include "PwXrslamTransportCore.h"
int main() {
  FakeXrslamReset();
  g_fake_intrinsics_mode = kFakeIntrinsicsConfigOnly;   // unmodified upstream core (generic)
  // session yaml K written from the same first-frame K (zero-ARKit runtime does this)
  const double k[4] = {1347.7943115234375, 1347.7943115234375, 957.4692993164062, 718.9641723632812};
  g_fake_config_intrinsics = {k[0], k[1], k[2], k[3]};
  if (PWXrslamTransportCreate("slam","device") != 1) return 2;
  std::array<uint8_t,64> px{}; int32_t st; PWXrslamRawPose p{};
  for (int i = 0; i < 5; ++i) PWXrslamTransportPushCameraAndRunRawWithIntrinsics(px.data(), 1.0+i, 8, 0, 4, k, &st, &p);
  PWXrslamIntrinsicsTrace t{}; PWXrslamTransportGetIntrinsicsTrace(&t);
  std::printf("upstream-core: attached=%llu engine_report_matched=%llu last_matches=%d\n",
    (unsigned long long)t.attached, (unsigned long long)t.engine_report_matched, t.last_engine_report_matches);
  PWXrslamTransportDestroyWithReceipt(nullptr);
}
