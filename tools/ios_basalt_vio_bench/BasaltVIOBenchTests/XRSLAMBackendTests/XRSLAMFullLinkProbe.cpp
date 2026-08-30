#if defined(PW_XRSLAM_FULL_LINK_PROBE) && PW_XRSLAM_FULL_LINK_PROBE

#include "../../XRSLAMBackend/Native/XRSLAMBench.h"

int main() { return xrslam_bench_backend_available() == 1 ? 0 : 1; }

#endif // PW_XRSLAM_FULL_LINK_PROBE
