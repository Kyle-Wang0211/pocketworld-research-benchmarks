// HOST-ONLY run test of ios/Runner/PwLodSurface.m against real Dawn (macOS Metal backend,
// the same dawn/native/metal/SharedTextureMemoryMTL.mm the phone runs). Scratchpad only.
// pwlod_gpu_create here = pw_lod_bench.cpp InitGpu (:159-217) + the caller's features, which is
// what the frozen header says the engine does. Only that one engine entry is provided.
#import "PwLodSurface.h"
#import <IOSurface/IOSurfaceRef.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static WGPUInstance g_inst;
static WGPUAdapter g_adapter;
static WGPUDevice g_device;
static int g_uncaptured = 0;

static void Wait(WGPUFuture f) {
  WGPUFutureWaitInfo w = {0};
  w.future = f;
  wgpuInstanceWaitAny(g_inst, 1, &w, UINT64_MAX);
}
static void OnAdapter(WGPURequestAdapterStatus st, WGPUAdapter a, WGPUStringView m, void* u1, void* u2) {
  (void)m; (void)u1; (void)u2; if (st == WGPURequestAdapterStatus_Success) g_adapter = a;
}
static void OnDevice(WGPURequestDeviceStatus st, WGPUDevice d, WGPUStringView m, void* u1, void* u2) {
  (void)u1; (void)u2; if (st == WGPURequestDeviceStatus_Success) g_device = d;
  else fprintf(stderr, "RequestDevice: %.*s\n", (int)m.length, m.data);
}
static void OnErr(const WGPUDevice* d, WGPUErrorType t, WGPUStringView m, void* u1, void* u2) {
  (void)d; (void)u1; (void)u2; g_uncaptured++;
  fprintf(stderr, "  [dawn uncaptured error type=%d] %.*s\n", (int)t, (int)m.length, m.data);
}

pwlod_status pwlod_gpu_create(const WGPUFeatureName* f, uint32_t n, pwlod_gpu* out) {
  memset(out, 0, sizeof *out);
  static const WGPUInstanceFeatureName kTimed = WGPUInstanceFeatureName_TimedWaitAny;
  WGPUInstanceDescriptor id = WGPU_INSTANCE_DESCRIPTOR_INIT;
  id.requiredFeatureCount = 1; id.requiredFeatures = &kTimed;
  if (!g_inst) g_inst = wgpuCreateInstance(&id);
  WGPURequestAdapterOptions ao = WGPU_REQUEST_ADAPTER_OPTIONS_INIT;
  ao.powerPreference = WGPUPowerPreference_HighPerformance;
  WGPURequestAdapterCallbackInfo aci = WGPU_REQUEST_ADAPTER_CALLBACK_INFO_INIT;
  aci.mode = WGPUCallbackMode_WaitAnyOnly; aci.callback = OnAdapter;
  g_adapter = NULL;
  Wait(wgpuInstanceRequestAdapter(g_inst, &ao, aci));
  if (!g_adapter) return PWLOD_ERR_GPU;
  WGPUDeviceDescriptor dd = WGPU_DEVICE_DESCRIPTOR_INIT;
  dd.requiredFeatureCount = n; dd.requiredFeatures = f;
  dd.uncapturedErrorCallbackInfo.callback = OnErr;
  WGPURequestDeviceCallbackInfo dci = WGPU_REQUEST_DEVICE_CALLBACK_INFO_INIT;
  dci.mode = WGPUCallbackMode_WaitAnyOnly; dci.callback = OnDevice;
  g_device = NULL;
  Wait(wgpuAdapterRequestDevice(g_adapter, &dd, dci));
  if (!g_device) return PWLOD_ERR_GPU;
  WGPUAdapterInfo info = WGPU_ADAPTER_INFO_INIT;
  wgpuAdapterGetInfo(g_adapter, &info);
  out->instance = g_inst; out->adapter = g_adapter; out->device = g_device;
  out->queue = wgpuDeviceGetQueue(g_device); out->backend = info.backendType;
  return PWLOD_OK;
}

static void OnDone(WGPUQueueWorkDoneStatus s, WGPUStringView m, void* u1, void* u2) { (void)s; (void)m; (void)u1; (void)u2; }

// Engine-style use of one target: BeginAccess, clear pass, submit, EndAccess, wait idle.
// Returns EndAccess status (BeginAccess failure -> -1).
static int RenderClear(const pwlod_gpu* g, const pwlod_target* t, double r, double gr, double b) {
  WGPUSharedTextureMemoryBeginAccessDescriptor bd = WGPU_SHARED_TEXTURE_MEMORY_BEGIN_ACCESS_DESCRIPTOR_INIT;
  bd.initialized = WGPU_FALSE;
  if (wgpuSharedTextureMemoryBeginAccess(t->memory, t->texture, &bd) != WGPUStatus_Success) return -1;
  WGPUTextureView view = wgpuTextureCreateView(t->texture, NULL);
  WGPURenderPassColorAttachment ca = WGPU_RENDER_PASS_COLOR_ATTACHMENT_INIT;
  ca.view = view; ca.loadOp = WGPULoadOp_Clear; ca.storeOp = WGPUStoreOp_Store;
  ca.clearValue = (WGPUColor){r, gr, b, 1.0};
  WGPURenderPassDescriptor rp = WGPU_RENDER_PASS_DESCRIPTOR_INIT;
  rp.colorAttachmentCount = 1; rp.colorAttachments = &ca;
  WGPUCommandEncoder enc = wgpuDeviceCreateCommandEncoder(g->device, NULL);
  WGPURenderPassEncoder pass = wgpuCommandEncoderBeginRenderPass(enc, &rp);
  wgpuRenderPassEncoderEnd(pass);
  WGPUCommandBuffer cb = wgpuCommandEncoderFinish(enc, NULL);
  wgpuQueueSubmit(g->queue, 1, &cb);
  WGPUSharedTextureMemoryEndAccessState es = WGPU_SHARED_TEXTURE_MEMORY_END_ACCESS_STATE_INIT;
  const WGPUStatus s = wgpuSharedTextureMemoryEndAccess(t->memory, t->texture, &es);
  wgpuSharedTextureMemoryEndAccessStateFreeMembers(es);
  WGPUQueueWorkDoneCallbackInfo wi = WGPU_QUEUE_WORK_DONE_CALLBACK_INFO_INIT;
  wi.mode = WGPUCallbackMode_WaitAnyOnly; wi.callback = OnDone;
  Wait(wgpuQueueOnSubmittedWorkDone(g->queue, wi));
  wgpuCommandBufferRelease(cb); wgpuRenderPassEncoderRelease(pass); wgpuCommandEncoderRelease(enc);
  wgpuTextureViewRelease(view);
  return (int)s;
}

// Reads the CVPixelBuffer Flutter would get. Returns #pixels equal to (b,g,r,255) and the
// per-channel std of the whole image (a flat image has std 0 -> not a pass by itself).
static long CountColor(CVPixelBufferRef pb, int B, int G, int R, double* chan_mean) {
  CVPixelBufferLockBaseAddress(pb, kCVPixelBufferLock_ReadOnly);
  const uint8_t* base = CVPixelBufferGetBaseAddress(pb);
  const size_t w = CVPixelBufferGetWidth(pb), h = CVPixelBufferGetHeight(pb), bpr = CVPixelBufferGetBytesPerRow(pb);
  long hit = 0; double s[3] = {0, 0, 0};
  for (size_t y = 0; y < h; y++) for (size_t x = 0; x < w; x++) {
    const uint8_t* p = base + y * bpr + x * 4;
    if (abs(p[0] - B) <= 1 && abs(p[1] - G) <= 1 && abs(p[2] - R) <= 1 && p[3] == 255) hit++;
    s[0] += p[0]; s[1] += p[1]; s[2] += p[2];
  }
  for (int c = 0; c < 3; c++) chan_mean[c] = s[c] / (double)(w * h);
  CVPixelBufferUnlockBaseAddress(pb, kCVPixelBufferLock_ReadOnly);
  return hit;
}

int main(void) {
  int fails = 0;
  const uint32_t W = 97, H = 61;  // odd width: exercises IOSurfaceAlignProperty
  printf("== A: PwLodSurfaceCreateGpu (IOSurface + MTLSharedEvent) ==\n");
  pwlod_gpu g;
  pwlod_status st = PwLodSurfaceCreateGpu(&g);
  printf("gpu status=%d backend=%d (Metal=%d)\n", (int)st, (int)g.backend, (int)WGPUBackendType_Metal);
  if (st != PWLOD_OK || g.backend != WGPUBackendType_Metal) return 1;
  char err[256] = {0};
  PwLodSurfaceRing* ring = PwLodSurfaceRingCreate(g.device, W, H, err, sizeof err);
  printf("ring=%p err='%s'\n", (void*)ring, err);
  if (!ring) return 1;
  const pwlod_target* t = PwLodSurfaceRingTargets(ring);
  const double col[3][3] = {{0.2, 0.4, 0.8}, {0.8, 0.2, 0.4}, {0.4, 0.8, 0.2}};
  for (int i = 0; i < PWLOD_TARGET_COUNT; i++) {
    CVPixelBufferRef pb = PwLodSurfaceRingPixelBuffer(ring, (uint32_t)i);
    IOSurfaceRef ios = CVPixelBufferGetIOSurface(pb);
    printf("slot %d: %zux%zu bpr=%zu fmt=0x%x texture=%p memory=%p\n", i, CVPixelBufferGetWidth(pb),
           CVPixelBufferGetHeight(pb), IOSurfaceGetBytesPerRow(ios), (unsigned)CVPixelBufferGetPixelFormatType(pb),
           (void*)t[i].texture, (void*)t[i].memory);
  }
  // NEGATIVE (before any render): slot 0 is not yet the target colour.
  double mean[3];
  const int B0 = (int)lround(col[0][2] * 255), G0 = (int)lround(col[0][1] * 255), R0 = (int)lround(col[0][0] * 255);
  long pre = CountColor(PwLodSurfaceRingPixelBuffer(ring, 0), B0, G0, R0, mean);
  printf("NEG unrendered slot0 hits=%ld/%u (must be 0)\n", pre, W * H);
  if (pre != 0) fails++;
  for (int i = 0; i < PWLOD_TARGET_COUNT; i++) {
    const int e = RenderClear(&g, &t[i], col[i][0], col[i][1], col[i][2]);
    const int B = (int)lround(col[i][2] * 255), G = (int)lround(col[i][1] * 255), R = (int)lround(col[i][0] * 255);
    long hit = CountColor(PwLodSurfaceRingPixelBuffer(ring, (uint32_t)i), B, G, R, mean);
    printf("slot %d: EndAccess=%d  BGRA hits=%ld/%u  mean B/G/R=%.1f/%.1f/%.1f (want %d/%d/%d)\n", i, e, hit,
           W * H, mean[0], mean[1], mean[2], B, G, R);
    if (e != (int)WGPUStatus_Success || hit != (long)W * H) fails++;
  }
  // NEGATIVE: slot 1's colour is not slot 0's (the three targets are three surfaces).
  long cross = CountColor(PwLodSurfaceRingPixelBuffer(ring, 1), B0, G0, R0, mean);
  printf("NEG slot1 with slot0's colour hits=%ld (must be 0)\n", cross);
  if (cross != 0) fails++;
  PwLodSurfaceRingDestroy(ring);
  pwlod_gpu_destroy(&g);
  printf("uncaptured errors so far: %d\n", g_uncaptured);
  if (g_uncaptured) fails++;

  printf("== B (NEGATIVE): device WITHOUT SharedFenceMTLSharedEvent ==\n");
  const WGPUFeatureName only_io[1] = {WGPUFeatureName_SharedTextureMemoryIOSurface};
  pwlod_gpu g2;
  st = pwlod_gpu_create(only_io, 1, &g2);
  PwLodSurfaceRing* ring2 = st == PWLOD_OK ? PwLodSurfaceRingCreate(g2.device, W, H, err, sizeof err) : NULL;
  printf("gpu status=%d ring=%p err='%s'\n", (int)st, (void*)ring2, ring2 ? "" : err);
  if (ring2) {
    const int before = g_uncaptured;
    const int e = RenderClear(&g2, &PwLodSurfaceRingTargets(ring2)[0], 0.2, 0.4, 0.8);
    printf("EndAccess status=%d (Success=%d) uncaptured errors=%d -> %s\n", e, (int)WGPUStatus_Success,
           g_uncaptured - before, e != (int)WGPUStatus_Success ? "refused as expected" : "NOT refused");
    if (e == (int)WGPUStatus_Success) fails++;
    PwLodSurfaceRingDestroy(ring2);
  } else {
    fails++;
  }
  printf("== B2 (NEGATIVE): device WITHOUT SharedTextureMemoryIOSurface -> import must fail ==\n");
  const WGPUFeatureName only_fence[1] = {WGPUFeatureName_SharedFenceMTLSharedEvent};
  pwlod_gpu g3;
  st = pwlod_gpu_create(only_fence, 1, &g3);
  PwLodSurfaceRing* ring3 = st == PWLOD_OK ? PwLodSurfaceRingCreate(g3.device, W, H, err, sizeof err) : NULL;
  printf("ring=%p err='%s' -> %s\n", (void*)ring3, err, ring3 ? "NOT refused" : "refused as expected");
  if (ring3) { fails++; PwLodSurfaceRingDestroy(ring3); }
  printf("RESULT %s (fails=%d)\n", fails ? "FAIL" : "PASS", fails);
  return fails ? 1 : 0;
}
