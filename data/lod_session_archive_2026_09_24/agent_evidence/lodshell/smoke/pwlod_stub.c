/* SMOKE-ONLY stub of the frozen engine ABI. Lives in the scratchpad, never in the repo.
   Includes the frozen headers so every prototype is compiler-checked against them. */
#include "pwlod_viewer.h"
#include "pw_lod_bench.h"
#include <string.h>
#if PWLOD_ABI_VERSION != 2
#error smoke stub is written against ABI v2
#endif
pwlod_status pwlod_gpu_create(const WGPUFeatureName* f, uint32_t n, pwlod_gpu* o) { (void)f; (void)n; memset(o, 0, sizeof *o); return PWLOD_ERR_GPU; }
void pwlod_gpu_destroy(pwlod_gpu* g) { (void)g; }
void pwlod_params_default(pwlod_params* o) { memset(o, 0, sizeof *o); }
pwlod_status pwlod_viewer_create(const pwlod_gpu* g, pwlod_viewer** o) { (void)g; *o = 0; return PWLOD_ERR_STATE; }
pwlod_status pwlod_viewer_load_octree(pwlod_viewer* v, const char* d) { (void)v; (void)d; return PWLOD_ERR_STATE; }
pwlod_status pwlod_viewer_set_params(pwlod_viewer* v, const pwlod_params* p) { (void)v; (void)p; return PWLOD_ERR_STATE; }
pwlod_status pwlod_viewer_set_camera(pwlod_viewer* v, const pwlod_camera* c) { (void)v; (void)c; return PWLOD_ERR_STATE; }
pwlod_status pwlod_viewer_set_targets(pwlod_viewer* v, const pwlod_target* t, uint32_t n, WGPUTextureFormat f, uint32_t w, uint32_t h) { (void)v; (void)t; (void)n; (void)f; (void)w; (void)h; return PWLOD_ERR_STATE; }
pwlod_status pwlod_viewer_start(pwlod_viewer* v, pwlod_frame_ready_fn fn, void* u) { (void)v; (void)fn; (void)u; return PWLOD_ERR_STATE; }
pwlod_status pwlod_viewer_acquire_latest(pwlod_viewer* v, uint32_t* i, uint64_t* f) { (void)v; (void)i; (void)f; return PWLOD_ERR_STATE; }
pwlod_status pwlod_viewer_stop(pwlod_viewer* v) { (void)v; return PWLOD_OK; }
pwlod_status pwlod_viewer_get_stats(pwlod_viewer* v, pwlod_frame_stats* s) { (void)v; if (s) { memset(s, 0, sizeof *s); s->lowest_spacing = 0.5; } return PWLOD_ERR_STATE; }
pwlod_status pwlod_viewer_render_once(pwlod_viewer* v, const pwlod_target* t, WGPUTextureFormat f, uint32_t w, uint32_t h, pwlod_frame_stats* s) { (void)v; (void)t; (void)f; (void)w; (void)h; (void)s; return PWLOD_ERR_STATE; }
void pwlod_viewer_destroy(pwlod_viewer* v) { (void)v; }
pwlod_status pwlod_build_from_ply(const char* p, const char* o, const char* c, int32_t b, int32_t t, pwlod_build_report* r, char* e, uint32_t n) { (void)p; (void)o; (void)c; (void)b; (void)t; (void)r; (void)e; (void)n; return PWLOD_ERR_IO; }
pwlod_status pwlod_verify_octree(const char* d, pwlod_verify_report* r) { (void)d; (void)r; return PWLOD_ERR_IO; }
const char* pwlod_version(void) { return "stub0000 abi=2"; }
const char* pwlod_run(const char* d, const char* o, const char* a, PwLodProbeFn p, void* c) { (void)d; (void)o; (void)a; (void)p; (void)c; return "stub"; }
