// pwofficial_pose_ab_driver.cc — HOST replay of the SHIPPING official SfM route
// (Aether3D 7dc00642 official_pipeline == a313ede0 == phone builds 165..169
// PWOfficialSfm, build stamp "Sep 16 2026 10:55:14") through the pwofficial_*
// ABI exactly as the capture page calls it, with the device pose prior swapped
// per arm (ARKit vs XRSLAM-converted). Everything else is identical per arm.
//
// Structure copied from (and cited):
//   Aether3D glomap_vendor/bench/sfm_replay_bench.cc  — create → add × N →
//     finalize_async → poll REFINED → final_diag / get_poses / get_points →
//     cloud.ply + aether_sfm_debug_dump_model (lines 404-556 @7dc00642)
//   Aether3D glomap_vendor/bench/sfm_scale_persist_driver.cc — the PRODUCTION
//     add_frame CPU-extraction entry with real gray + real pose + per-frame K
//     (lines 205-226 @7dc00642), host GPU-symbol stubs (lines 41-60).
// Differences from those drivers (deliberate):
//   * calls the shipped shim (pocketworld 4e22ee7 vendor/official_sfm/src/
//     pwofficial_export_shim.c) instead of aether_sfm_* directly;
//   * gray comes from the recording's raw luma8 stream (frames.bin, 1920x1440,
//     recording_manifest.json "luma8_from_420f_full_range"), one frame =
//     W*H bytes at byteOffset (frames.pwvi "offset"/"len");
//   * options = the shipping capture tier: max_features 13312, K 12
//     (pocketworld feat/dense-stage lib/official_aether_sfm_ffi.dart:1044-1045,
//      lib/official_capture/sfm_live_recon.dart:1973), match ratio = core
//     default; use_gpu_extract = 0 (host has no Dawn extractor: CPU DSP-SIFT
//     fallback inside the core); use_gpu_match = 1 via the shipped Metal matcher
//     source compiled for macOS (same bytes as vendor pwofficial_gpu_match.mm).
//
// usage: pwofficial_pose_ab_driver <frames.bin> <feed.jsonl> <out_dir>
//            [--max-features=13312] [--k=12] [--gpu-match=1]
// [TASKB-JPEG 2026-09-24] step2 host-only addition: <frames.bin> = the literal
// JPEG ⇒ every feed line carries "jpeg": "<path>" and the gray plane is decoded
// from that 12 MP phone JPEG with portable libjpeg (out_color_space =
// JCS_GRAYSCALE, i.e. the JFIF Y plane) instead of a pre-extracted frames.bin
// (a 190-frame 12 MP frames.bin would need 2.3 GB of disk). Deviation from
// production: production decodes the same JPEG inside the core boundary
// (official_sfm_io_c.h pwofficial_add_jpeg_frame, "full-resolution luma
// plane"); decoder/rounding differences are ±1 LSB-level.
// [TASKB-RESUME 2026-09-24] step2 host-only addition: <frames.bin> = the literal
// RESUME ⇒ <out_dir>/session.db (+ .arkit_pose_v1) must already hold a COPY of a
// phone capture's database and pose store; no frame is added. finalize_async
// then takes the core's own resume route (RebuildFrameRecordsForResume:
// every frame restored at its stored device pose, TriangulateImage over the db
// matches, then RefineGlobalBA) — the route production's sfm_resume.dart uses
// to re-finalize a capture straight from its db. The feed only supplies the
// image size and the frame count.

#include "official_sfm_c.h"  // pocketworld 4e22ee7 vendor header (pwofficial_*)

#include <glog/logging.h>
#include <jpeglib.h>
#include <CoreFoundation/CoreFoundation.h>
#include <CoreGraphics/CoreGraphics.h>
#include <ImageIO/ImageIO.h>

#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

// Core diagnostics that the shim does not re-export (host-only reads; same
// functions sfm_replay_bench.cc uses: lines 525-551 @7dc00642).
extern "C" void aether_sfm_final_diag(aether_sfm_session_t* s,
                                      double* mean_reproj_px,
                                      int64_t* n_points, int64_t* n_track3plus,
                                      int64_t* n_obs);
extern "C" aether_sfm_result_t aether_sfm_debug_dump_model(
    aether_sfm_session_t* s, const char* out_dir);
extern "C" const char* aether_sfm_result_str(aether_sfm_result_t r);
// [DEVICE-ALIGN-V1 2026-09-24] step2 workspace addition: read the new core
// accessor (official_pipeline/include/aether_sfm_c.h) after REFINED.
// [fixD] shipping core has no device-alignment accessor: weak no-op definition (status -1).
extern "C" __attribute__((weak)) int aether_sfm_device_alignment_v1(
    aether_sfm_session_t*, double*, double*, int*, int*, double*, double*, double*, double*) { return -1; }

// ─── host GPU-symbol stubs (verbatim rationale: sfm_scale_persist_driver.cc
// 41-60 @7dc00642). The Dawn extractor exists only in the iOS carrier; the
// real host Metal matcher object renames its set_preview_fps30 to *_hostimpl
// (glomap_vendor/CMakeLists.txt:1143-1149), so the strong no-op lives here.
#if !defined(FIXD_REAL_GPU_EXTRACT)
extern "C" int aether_dsp_sift_extract_gpu(const uint8_t*, int, int, int, int,
                                           float*, uint8_t*, int, int*) {
  return -1;  // GPU extractor unavailable → add_frame falls back to CPU
}
extern "C" int aether_dsp_sift_extract_gpu_v2(const uint8_t*, int, int, int,
                                              int, float*, uint8_t*, float*,
                                              float*, int, int*) {
  return -1;
}
extern "C" void aether_sed_last_stages(double*, int) {}
#endif
extern "C" void aether_gpu_match_set_preview_fps30(int) {}
#if !defined(FIXD_REAL_GPU_EXTRACT)
extern "C" const char* aether_sed_last_fail_reason(void) { return nullptr; }
#endif

namespace {

double NowMs() {
  using namespace std::chrono;
  return duration<double, std::milli>(steady_clock::now().time_since_epoch())
      .count();
}

std::string ArgS(int argc, char** argv, const char* key, const char* def) {
  const size_t kl = std::strlen(key);
  for (int i = 1; i < argc; ++i)
    if (std::strncmp(argv[i], key, kl) == 0) {
      const char* eq = std::strchr(argv[i], '=');
      if (eq) return std::string(eq + 1);
    }
  return std::string(def);
}

bool ParseArray(const std::string& line, const char* key, double* out, int n) {
  const size_t k = line.find(key);
  if (k == std::string::npos) return false;
  const size_t lb = line.find('[', k);
  if (lb == std::string::npos) return false;
  const char* p = line.c_str() + lb + 1;
  char* end = nullptr;
  for (int i = 0; i < n; ++i) {
    out[i] = std::strtod(p, &end);
    if (end == p) return false;
    p = end;
    while (*p == ',' || *p == ' ') ++p;
  }
  return true;
}

bool ParseI64(const std::string& line, const char* key, long long* out) {
  const size_t k = line.find(key);
  if (k == std::string::npos) return false;
  *out = std::atoll(line.c_str() + k + std::strlen(key));
  return true;
}

struct Feed {
  std::string jpeg;  // [TASKB-JPEG]
  long long frame_index = -1, byte_offset = -1, w = 0, h = 0;
  double k[4] = {0, 0, 0, 0};
  double q[4] = {1, 0, 0, 0};
  double t[3] = {0, 0, 0};
};

std::vector<Feed> LoadFeed(const std::string& path) {
  std::vector<Feed> v;
  std::ifstream in(path);
  std::string line;
  while (std::getline(in, line)) {
    Feed f;
    if (!ParseI64(line, "\"frameIndex\": ", &f.frame_index)) continue;
    ParseI64(line, "\"byteOffset\": ", &f.byte_offset);
    ParseI64(line, "\"w\": ", &f.w);
    ParseI64(line, "\"h\": ", &f.h);
    {  // [TASKB-JPEG]
      const size_t k = line.find("\"jpeg\": \"");
      if (k != std::string::npos) {
        const size_t b = k + 9, e = line.find('"', b);
        f.jpeg = line.substr(b, e - b);
      }
    }
    const bool ok = ParseArray(line, "\"fxfycxcy\":", f.k, 4) &&
                    ParseArray(line, "\"arkitCamFromWorldQwxyz\":", f.q, 4) &&
                    ParseArray(line, "\"arkitCamFromWorldTxyz\":", f.t, 3);
    if (!ok || (f.byte_offset < 0 && f.jpeg.empty()) || f.w <= 0 || f.h <= 0) {
      std::fprintf(stderr, "bad feed line: %s\n", line.c_str());
      std::exit(2);
    }
    v.push_back(f);
  }
  return v;
}

// [fixD] phone-identical decode: pw-dense-stage vendor/official_sfm/src/pwofficial_jpeg_decode.mm:48-110
// (CGImageSource -> CGBitmapContext DeviceGray, kCGInterpolationNone, no EXIF rotation).
bool DecodeCGGray(const std::string& path, long long w, long long h, std::vector<uint8_t>* out) {
  CFURLRef url = CFURLCreateFromFileSystemRepresentation(kCFAllocatorDefault, reinterpret_cast<const UInt8*>(path.c_str()), (CFIndex)path.size(), false);
  if (!url) return false;
  CGImageSourceRef src = CGImageSourceCreateWithURL(url, nullptr); CFRelease(url);
  if (!src) return false;
  CGImageRef img = CGImageSourceCreateImageAtIndex(src, 0, nullptr); CFRelease(src);
  if (!img) return false;
  if ((long long)CGImageGetWidth(img) != w || (long long)CGImageGetHeight(img) != h) { CGImageRelease(img); return false; }
  out->assign((size_t)w * (size_t)h, 0);
  CGColorSpaceRef cs = CGColorSpaceCreateDeviceGray();
  CGContextRef ctx = CGBitmapContextCreate(out->data(), (size_t)w, (size_t)h, 8, (size_t)w, cs, kCGImageAlphaNone);
  CGColorSpaceRelease(cs);
  CGContextSetInterpolationQuality(ctx, kCGInterpolationNone);
  CGContextDrawImage(ctx, CGRectMake(0, 0, (CGFloat)w, (CGFloat)h), img);
  CGContextRelease(ctx); CGImageRelease(img);
  return true;
}

// [TASKB-JPEG] libjpeg grayscale decode (libjpeg example.c pattern).
bool DecodeJpegLuma(const std::string& path, long long w, long long h,
                    std::vector<uint8_t>* out) {
  std::FILE* f = std::fopen(path.c_str(), "rb");
  if (!f) return false;
  jpeg_decompress_struct cinfo;
  jpeg_error_mgr jerr;
  cinfo.err = jpeg_std_error(&jerr);
  jpeg_create_decompress(&cinfo);
  jpeg_stdio_src(&cinfo, f);
  jpeg_read_header(&cinfo, TRUE);
  cinfo.out_color_space = JCS_GRAYSCALE;
  jpeg_start_decompress(&cinfo);
  const bool dims_ok = static_cast<long long>(cinfo.output_width) == w &&
                       static_cast<long long>(cinfo.output_height) == h &&
                       cinfo.output_components == 1;
  if (dims_ok) {
    out->resize(static_cast<size_t>(w) * static_cast<size_t>(h));
    while (cinfo.output_scanline < cinfo.output_height) {
      JSAMPROW row = out->data() + static_cast<size_t>(cinfo.output_scanline) *
                                       static_cast<size_t>(w);
      jpeg_read_scanlines(&cinfo, &row, 1);
    }
    jpeg_finish_decompress(&cinfo);
  }
  jpeg_destroy_decompress(&cinfo);
  std::fclose(f);
  return dims_ok;
}

void WritePly(const std::string& path, const aether_sfm_point_t* pts, int n) {
  // verbatim from sfm_replay_bench.cc:173-186 @7dc00642
  std::ofstream out(path, std::ios::binary);
  out << "ply\nformat binary_little_endian 1.0\n";
  out << "element vertex " << n << "\n";
  out << "property float x\nproperty float y\nproperty float z\n";
  out << "property uchar red\nproperty uchar green\nproperty uchar blue\n";
  out << "end_header\n";
  for (int i = 0; i < n; ++i) {
    out.write(reinterpret_cast<const char*>(&pts[i].x), sizeof(float) * 3);
    out.write(reinterpret_cast<const char*>(&pts[i].r), 1);
    out.write(reinterpret_cast<const char*>(&pts[i].g), 1);
    out.write(reinterpret_cast<const char*>(&pts[i].b), 1);
  }
}

}  // namespace

int main(int argc, char** argv) {
  google::InitGoogleLogging(argv[0]);
  FLAGS_logtostderr = 1;
  if (argc < 4) {
    std::fprintf(stderr,
                 "usage: %s <frames.bin> <feed.jsonl> <out_dir> "
                 "[--max-features=13312] [--k=12] [--gpu-match=1]\n",
                 argv[0]);
    return 1;
  }
  const std::string frames_bin = argv[1];
  const std::string feed_path = argv[2];
  const std::string out_dir = argv[3];
  const int max_features =
      std::atoi(ArgS(argc, argv, "--max-features", "13312").c_str());
  const int k = std::atoi(ArgS(argc, argv, "--k", "12").c_str());
  const int gpu_match = std::atoi(ArgS(argc, argv, "--gpu-match", "1").c_str());

  const std::vector<Feed> feed = LoadFeed(feed_path);
  if (feed.empty()) {
    std::fprintf(stderr, "empty feed\n");
    return 2;
  }
  const bool jpeg_mode = frames_bin == "JPEG";  // [TASKB-JPEG]
  const bool resume_mode = frames_bin == "RESUME";  // [TASKB-RESUME]
  std::FILE* fb = (jpeg_mode || resume_mode)
                      ? nullptr
                      : std::fopen(frames_bin.c_str(), "rb");
  if (!fb && !jpeg_mode && !resume_mode) {
    std::fprintf(stderr, "cannot open %s\n", frames_bin.c_str());
    return 2;
  }

  aether_sfm_options_t opt;
  pwofficial_options_default(&opt);
  opt.max_features = max_features;
  opt.k_neighbors = k;
  opt.image_width = static_cast<int>(feed[0].w);
  opt.image_height = static_cast<int>(feed[0].h);
  opt.use_gpu_extract = std::getenv("FIXD_GPU_EXTRACT") ? std::atoi(std::getenv("FIXD_GPU_EXTRACT")) : 0;  // [fixD]
  opt.use_gpu_match = gpu_match;
  std::printf("DRIVER feed=%s n=%zu max_features=%d k=%d ratio=%.3f "
              "gpu_match=%d gpu_extract=0 size=%dx%d\n",
              feed_path.c_str(), feed.size(), opt.max_features,
              opt.k_neighbors, opt.match_max_ratio, opt.use_gpu_match,
              opt.image_width, opt.image_height);
  std::fflush(stdout);

  const std::string sess_db = out_dir + "/session.db";
  if (!resume_mode) std::remove(sess_db.c_str());  // [TASKB-RESUME] keep copy
  aether_sfm_session_t* s = nullptr;
  aether_sfm_result_t rc = pwofficial_create(sess_db.c_str(), &opt, &s);
  if (rc != AETHER_SFM_OK || !s) {
    std::fprintf(stderr, "pwofficial_create failed: %s\n",
                 aether_sfm_result_str(rc));
    return 2;
  }

  std::FILE* per_frame = std::fopen((out_dir + "/per_frame.jsonl").c_str(), "w");
  std::vector<uint8_t> gray;
  int fed = 0, rejected = 0;
  const double t_stream0 = NowMs();
  for (const Feed& f : feed) {
    if (resume_mode) break;  // [TASKB-RESUME] frames come from the db copy
    const size_t n = static_cast<size_t>(f.w) * static_cast<size_t>(f.h);
    gray.resize(n);
    if (jpeg_mode) {  // [TASKB-JPEG]
      if (!(std::getenv("FIXD_DECODE") && std::string(std::getenv("FIXD_DECODE")) == "cg" ? DecodeCGGray(f.jpeg, f.w, f.h, &gray) : DecodeJpegLuma(f.jpeg, f.w, f.h, &gray))) {
        std::fprintf(stderr, "jpeg decode failed frame %lld %s\n",
                     f.frame_index, f.jpeg.c_str());
        return 3;
      }
    } else if (fseeko(fb, static_cast<off_t>(f.byte_offset), SEEK_SET) != 0 ||
        std::fread(gray.data(), 1, n, fb) != n) {
      std::fprintf(stderr, "short read frame %lld\n", f.frame_index);
      return 3;
    }
    int out_fid = -1;
    const double t0 = NowMs();
    rc = pwofficial_add_frame(s, gray.data(), static_cast<int>(f.w),
                              static_cast<int>(f.h), static_cast<float>(f.k[0]),
                              static_cast<float>(f.k[1]),
                              static_cast<float>(f.k[2]),
                              static_cast<float>(f.k[3]), f.q, f.t, &out_fid);
    const double add_ms = NowMs() - t0;
    double ex_ms = 0, mt_ms = 0;
    int n_cand = 0, gm = 0, cm = 0;
    pwofficial_debug_last(s, &ex_ms, &mt_ms, &n_cand, &gm, &cm);
    std::fprintf(per_frame,
                 "{\"frameIndex\":%lld,\"rc\":\"%s\",\"fid\":%d,"
                 "\"add_ms\":%.1f,\"extract_ms\":%.1f,\"match_ms\":%.1f,"
                 "\"n_cand\":%d,\"gpu_matches\":%d,\"cpu_matches\":%d}\n",
                 f.frame_index, aether_sfm_result_str(rc), out_fid, add_ms,
                 ex_ms, mt_ms, n_cand, gm, cm);
    std::fflush(per_frame);
    if (rc != AETHER_SFM_OK) {
      ++rejected;
      std::fprintf(stderr, "frame %lld: add failed: %s\n", f.frame_index,
                   aether_sfm_result_str(rc));
      continue;
    }
    ++fed;
    std::printf("  fed %d/%zu frame=%lld fid=%d add_ms=%.0f cand=%d\n", fed,
                feed.size(), f.frame_index, out_fid, add_ms, n_cand);
    std::fflush(stdout);
  }
  std::fclose(per_frame);
  if (fb) std::fclose(fb);
  const double stream_ms = NowMs() - t_stream0;

  int64_t tvg = 0, raw = 0, ga = 0, gr = 0, rf = 0, tf = 0, x[31] = {0};
  pwofficial_stream_stats(s, &tvg, &raw, &ga, &gr, &rf, &tf, &x[0], &x[1],
                          &x[2], &x[3], &x[4], &x[5], &x[6], &x[7], &x[8],
                          &x[9], &x[10], &x[11], &x[12], &x[13], &x[14],
                          &x[15], &x[16], &x[17], &x[18], &x[19], &x[20],
                          &x[21], &x[22], &x[23], &x[24], &x[25], &x[26],
                          &x[27], &x[28], &x[29]);
  int64_t sp_first = 0, temporal_fb = 0;
  pwofficial_candidate_stats(s, &sp_first, &temporal_fb);
  std::printf("STREAMED fed=%d rejected=%d stream_ms=%.1f tvg_pairs=%lld "
              "raw_pairs=%lld grow_acc=%lld grow_rej=%lld spatial_first=%lld "
              "temporal_fallback=%lld spatial_attempted=%lld "
              "spatial_written=%lld spatial_inliers=%lld\n",
              fed, rejected, stream_ms, (long long)tvg, (long long)raw,
              (long long)ga, (long long)gr, (long long)sp_first,
              (long long)temporal_fb, (long long)x[10], (long long)x[11],
              (long long)x[12]);
  std::fflush(stdout);

  char fj[1024] = {0};
  const double t_fin0 = NowMs();
  rc = pwofficial_finalize_async(s, fj, sizeof(fj));
  if (rc != AETHER_SFM_OK) {
    std::fprintf(stderr, "finalize_async failed: %s\n",
                 aether_sfm_result_str(rc));
    std::printf("RESULT finalize=ASYNC_FAILED rc=%s\n",
                aether_sfm_result_str(rc));
    pwofficial_free(s);
    return 4;
  }
  std::printf("FINALIZE_ASYNC phase1=%s\n", fj);
  std::fflush(stdout);
  int status = pwofficial_finalize_status(s);
  while (status != 2 && status != 3) {
    std::this_thread::sleep_for(std::chrono::milliseconds(200));
    status = pwofficial_finalize_status(s);
  }
  const double finalize_ms = NowMs() - t_fin0;
  std::printf("FINALIZE status=%d finalize_ms=%.1f\n", status, finalize_ms);
  std::fflush(stdout);
  if (status == 3) {
    std::printf("RESULT finalize=ERROR fed=%d rejected=%d stream_ms=%.1f "
                "finalize_ms=%.1f\n",
                fed, rejected, stream_ms, finalize_ms);
    pwofficial_free(s);
    return 5;
  }

  double reproj = -1;
  int64_t npts = 0, ntrack3 = 0, nobs = 0;
  aether_sfm_final_diag(s, &reproj, &npts, &ntrack3, &nobs);
  {
    double da_scale = 0, da_maxe = 0, da_cmed = 0, da_cmax = 0, da_rmed = 0,
           da_rmax = 0;
    int da_n = 0, da_in = 0;
    {
    const int da_status = aether_sfm_device_alignment_v1(
        s, &da_scale, &da_maxe, &da_n, &da_in, &da_cmed, &da_cmax, &da_rmed,
        &da_rmax);
    std::printf("DEVICE_ALIGN status=%d scale=%.9f max_error_m=%.6f "
                "pairs=%d inliers=%d centre_err_median_mm=%.3f "
                "centre_err_max_mm=%.3f rot_err_median_deg=%.4f "
                "rot_err_max_deg=%.4f\n",
                da_status, da_scale, da_maxe, da_n, da_in, da_cmed * 1e3,
                da_cmax * 1e3, da_rmed, da_rmax);
    std::fflush(stdout);
    }
  }
  std::vector<aether_sfm_pose_t> poses(feed.size() + 8);
  int n_pose = 0;
  pwofficial_get_poses(s, poses.data(), static_cast<int>(poses.size()),
                       &n_pose);
  int n_reg = 0;
  std::FILE* pf = std::fopen((out_dir + "/delivered_poses.txt").c_str(), "w");
  for (int i = 0; i < n_pose; ++i) {
    if (poses[i].registered) ++n_reg;
    // frame_id == feed row order (out_fid); map back to recording frameIndex.
    const int fid = poses[i].frame_id;
    const long long fi =
        (fid >= 0 && fid < static_cast<int>(feed.size())) ? feed[fid].frame_index
                                                          : -1;
    std::fprintf(pf, "%d %lld %d %.17g %.17g %.17g %.17g %.17g %.17g %.17g\n",
                 fid, fi, poses[i].registered, poses[i].qwxyz[0],
                 poses[i].qwxyz[1], poses[i].qwxyz[2], poses[i].qwxyz[3],
                 poses[i].t[0], poses[i].t[1], poses[i].t[2]);
  }
  std::fclose(pf);
  aether_sfm_point_t* pts = nullptr;
  int n_pts = 0;
  pwofficial_get_points(s, &pts, &n_pts);
  WritePly(out_dir + "/cloud.ply", pts, n_pts);
  pwofficial_points_free(pts);
  aether_sfm_debug_dump_model(s, out_dir.c_str());

  std::printf("RESULT finalize=REFINED fed=%d rejected=%d n_reg=%d/%d "
              "n_points=%lld track3plus=%lld n_obs=%lld mean_reproj_px=%.4f "
              "cloud_points=%d stream_ms=%.1f finalize_ms=%.1f total_ms=%.1f\n",
              fed, rejected, n_reg, n_pose, (long long)npts,
              (long long)ntrack3, (long long)nobs, reproj, n_pts, stream_ms,
              finalize_ms, stream_ms + finalize_ms);
  std::fflush(stdout);
  pwofficial_free(s);
  return 0;
}
