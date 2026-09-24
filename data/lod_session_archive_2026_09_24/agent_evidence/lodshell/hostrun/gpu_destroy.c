#include "pwlod_viewer.h"
void pwlod_gpu_destroy(pwlod_gpu* g) { if (!g) return; if (g->queue) wgpuQueueRelease(g->queue); if (g->device) wgpuDeviceRelease(g->device); }
