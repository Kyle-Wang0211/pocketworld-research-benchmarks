// offline_pose_arm_driver.cc — [offline_sfm 2026-09-25] 在 Mac 上跑**出货 SfM 核二进制**
// (pocketworld bench/full-chain-168-fixes@3f28853 的 PWOfficialSfm.xcframework/ios-arm64,
// = Aether3D a313ede0 + 补丁 B + fixC 核 + fixD 载体;只把 LC_BUILD_VERSION 平台 iOS→macOS
// 改标签并临时签名,22 个节逐字节不变),同一组照片、只换设备位姿的对照驱动。
//
// 底本:研究仓 data/rootcause-fixes-20260924@8cb0ca9
//   fixC_core_reg_evidence/driver/pwofficial_pose_ab_driver.cc(create → add × N →
//   finalize_async → 轮询 REFINED → get_poses / get_points)。与底本的差别(逐条):
//   * 只调用出货框架**导出**的 pwofficial_* 符号。底本另用的 aether_sfm_final_diag /
//     aether_sfm_debug_dump_model / aether_sfm_result_str / aether_sfm_device_alignment_v1
//     不在出货二进制里(未导出且被链接器剥掉);交付 Sim3 对齐结果改从核自己写的
//     诊断 jsonl(补丁 B:AppendMatchFailJsonl 的 "device_alignment_v1" 一行)读取;
//     结果码字符串在本文件按头文件枚举自写。
//   * 喂帧 = 产品入口 pwofficial_add_jpeg_frame_v2 的逐句复刻(pocketworld 3f28853
//     vendor/official_sfm/src/pwofficial_jpeg_decode.mm:144-225):同样的参数校验 →
//     DecodeOfficialJpegGray(ImageIO 解码,画进 DeviceGray 8 位位图,插值 None,不应用
//     EXIF 朝向)→ 出货核导出的 pwofficial_add_frame_v2(fixA 契约:pose_t 之后的
//     int32 device_pose_trusted)。唯一偏离:出货解码函数硬性要求 4032x3024(:77-81),
//     本次照片是 1920x1440 视频帧(用户 09-25 定的口径),所以复刻里去掉了这一条尺寸检查。
//     不能直接调框架里的 pwofficial_add_jpeg_frame_v2:它会以 ERR_INVALID_ARG 拒掉 1920x1440。
//   * 不再需要主机 GPU 桩函数:出货框架自带 Dawn GPU 提取载体与 Metal 匹配器。
//   * 选项 = 产品研究档(pocketworld 3f28853 lib/official_aether_sfm_ffi.dart:1100-1135):
//     max_features 13312、K 12、match_max_ratio 0.8、use_gpu_match 1、use_gpu_extract 1
//     (--gpu-extract=0 可退回核内 CPU DSP-SIFT)。
//   * 另导出带观测的点(pwofficial_get_points_tracked),供离线算重投影误差。
//
// 用法:offline_pose_arm_driver <feed.jsonl> <out_dir> [--gpu-extract=1] [--gpu-match=1]
//   feed 每行:{"frameIndex":i,"jpeg":"...","t":秒,"w":W,"h":H,"fxfycxcy":[..],
//              "arkitCamFromWorldQwxyz":[w,x,y,z],"arkitCamFromWorldTxyz":[..],
//              "devicePoseTrusted":true|false}
#include "official_sfm_c.h"
#include "official_sfm_io_c.h"

#include <CoreFoundation/CoreFoundation.h>
#include <CoreGraphics/CoreGraphics.h>
#include <ImageIO/ImageIO.h>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

// 出货框架导出、出货头文件未声明(原型抄 fixC patch_C_pocketworld_side_v2_abi.diff:62-80 注释
// 与 fixC 驱动的调用:pwofficial_add_frame 的参数 + pose_t 之后的 device_pose_trusted)。
extern "C" aether_sfm_result_t pwofficial_add_frame_v2(
    aether_sfm_session_t* session, const uint8_t* gray, int width, int height,
    float fx, float fy, float cx, float cy, const double pose_qwxyz[4],
    const double pose_t[3], int32_t device_pose_trusted, int* out_frame_id);
extern "C" void pwofficial_registration_evidence_stats_v1(
    aether_sfm_session_t* s, int64_t* untrusted_fed, int64_t* untrusted_registered,
    int64_t* evidence_checked, int64_t* evidence_failed, int64_t* late_registered,
    int64_t* unregistered_delivered);

namespace {

// pwofficial_jpeg_decode.mm:48-111 DecodeOfficialJpegGray 逐句复刻,只删 4032x3024 检查(见文件头)。
aether_sfm_result_t DecodeOfficialJpegGrayAnySize(const char* jpeg_path, std::vector<uint8_t>* gray,
                                                  int* out_width, int* out_height) {
  if (jpeg_path == nullptr || jpeg_path[0] == '\0' || gray == nullptr || out_width == nullptr ||
      out_height == nullptr) {
    return AETHER_SFM_ERR_INVALID_ARG;
  }
  CFURLRef url = CFURLCreateFromFileSystemRepresentation(
      kCFAllocatorDefault, reinterpret_cast<const UInt8*>(jpeg_path),
      static_cast<CFIndex>(std::strlen(jpeg_path)), false);
  if (url == nullptr) return AETHER_SFM_ERR_INVALID_ARG;
  CGImageSourceRef source = CGImageSourceCreateWithURL(url, nullptr);
  CFRelease(url);
  if (source == nullptr) return AETHER_SFM_ERR_EXTRACT;
  CGImageRef image = CGImageSourceCreateImageAtIndex(source, 0, nullptr);
  CFRelease(source);
  if (image == nullptr) return AETHER_SFM_ERR_EXTRACT;
  const size_t width = CGImageGetWidth(image);
  const size_t height = CGImageGetHeight(image);
  // [偏离] 出货此处:if (width != 4032 || height != 3024) return AETHER_SFM_ERR_INVALID_ARG;
  try {
    gray->assign(width * height, 0);
  } catch (...) {
    CGImageRelease(image);
    return AETHER_SFM_ERR_EXTRACT;
  }
  CGColorSpaceRef color_space = CGColorSpaceCreateDeviceGray();
  if (color_space == nullptr) {
    CGImageRelease(image);
    return AETHER_SFM_ERR_EXTRACT;
  }
  CGContextRef context =
      CGBitmapContextCreate(gray->data(), width, height, 8, width, color_space, kCGImageAlphaNone);
  CGColorSpaceRelease(color_space);
  if (context == nullptr) {
    CGImageRelease(image);
    return AETHER_SFM_ERR_EXTRACT;
  }
  CGContextSetInterpolationQuality(context, kCGInterpolationNone);
  CGContextDrawImage(context, CGRectMake(0, 0, static_cast<CGFloat>(width), static_cast<CGFloat>(height)),
                     image);
  CGContextRelease(context);
  CGImageRelease(image);
  *out_width = static_cast<int>(width);
  *out_height = static_cast<int>(height);
  return AETHER_SFM_OK;
}

// pwofficial_add_jpeg_frame_v2(pwofficial_jpeg_decode.mm:188-225)逐句复刻,解码换成上面那份。
aether_sfm_result_t AddJpegFrameV2AnySize(aether_sfm_session_t* session, const char* jpeg_path,
                                          double capture_timestamp, float fx, float fy, float cx, float cy,
                                          const double pose_qwxyz[4], const double pose_t[3],
                                          int32_t device_pose_trusted, int* out_frame_id) {
  if (session == nullptr || jpeg_path == nullptr || jpeg_path[0] == '\0' ||
      !std::isfinite(capture_timestamp) || capture_timestamp < 0.0) {
    return AETHER_SFM_ERR_INVALID_ARG;
  }
  std::vector<uint8_t> gray;
  int width = 0;
  int height = 0;
  const aether_sfm_result_t decode = DecodeOfficialJpegGrayAnySize(jpeg_path, &gray, &width, &height);
  if (decode != AETHER_SFM_OK) return decode;
  return pwofficial_add_frame_v2(session, gray.data(), width, height, fx, fy, cx, cy, pose_qwxyz, pose_t,
                                 device_pose_trusted, out_frame_id);
}

const char* ResultStr(aether_sfm_result_t r) {
  switch (r) {
    case AETHER_SFM_OK: return "OK";
    case AETHER_SFM_ERR_INVALID_ARG: return "ERR_INVALID_ARG";
    case AETHER_SFM_ERR_DB: return "ERR_DB";
    case AETHER_SFM_ERR_EXTRACT: return "ERR_EXTRACT";
    case AETHER_SFM_ERR_NO_INITIAL_PAIR: return "ERR_NO_INITIAL_PAIR";
    case AETHER_SFM_ERR_NOT_REGISTERED: return "ERR_NOT_REGISTERED";
    case AETHER_SFM_ERR_INTERNAL: return "ERR_INTERNAL";
    case AETHER_SFM_ERR_UNSUPPORTED: return "ERR_UNSUPPORTED";
  }
  return "ERR_UNKNOWN";
}

double NowMs() {
  using namespace std::chrono;
  return duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
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

bool ParseNum(const std::string& line, const char* key, double* out) {
  const size_t k = line.find(key);
  if (k == std::string::npos) return false;
  *out = std::strtod(line.c_str() + k + std::strlen(key), nullptr);
  return true;
}

struct Feed {
  std::string jpeg;
  bool trusted = true;
  long long frame_index = -1, w = 0, h = 0;
  double ts = 0;
  double k[4] = {0, 0, 0, 0};
  double q[4] = {1, 0, 0, 0};
  double t[3] = {0, 0, 0};
};

std::vector<Feed> LoadFeed(const std::string& path) {
  std::vector<Feed> v;
  std::ifstream in(path);
  std::string line;
  while (std::getline(in, line)) {
    if (line.empty()) continue;
    Feed f;
    double d = 0;
    if (!ParseNum(line, "\"frameIndex\": ", &d)) continue;
    f.frame_index = static_cast<long long>(d);
    if (ParseNum(line, "\"w\": ", &d)) f.w = static_cast<long long>(d);
    if (ParseNum(line, "\"h\": ", &d)) f.h = static_cast<long long>(d);
    ParseNum(line, "\"t\": ", &f.ts);
    const size_t kj = line.find("\"jpeg\": \"");
    if (kj != std::string::npos) {
      const size_t b = kj + 9, e = line.find('"', b);
      f.jpeg = line.substr(b, e - b);
    }
    if (line.find("\"devicePoseTrusted\": false") != std::string::npos) f.trusted = false;
    const bool ok = ParseArray(line, "\"fxfycxcy\":", f.k, 4) &&
                    ParseArray(line, "\"arkitCamFromWorldQwxyz\":", f.q, 4) &&
                    ParseArray(line, "\"arkitCamFromWorldTxyz\":", f.t, 3);
    if (!ok || f.jpeg.empty() || f.w <= 0 || f.h <= 0) {
      std::fprintf(stderr, "bad feed line: %s\n", line.c_str());
      std::exit(2);
    }
    v.push_back(f);
  }
  return v;
}

void WritePly(const std::string& path, const aether_sfm_point_t* pts, int n) {
  // 底本 WritePly(= sfm_replay_bench.cc:173-186 @7dc00642)原样
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
  if (argc < 3) {
    std::fprintf(stderr, "usage: %s <feed.jsonl> <out_dir> [--gpu-extract=1] [--gpu-match=1]\n", argv[0]);
    return 1;
  }
  const std::string feed_path = argv[1];
  const std::string out_dir = argv[2];
  const int gpu_extract = std::atoi(ArgS(argc, argv, "--gpu-extract", "1").c_str());
  const int gpu_match = std::atoi(ArgS(argc, argv, "--gpu-match", "1").c_str());
  const std::vector<Feed> feed = LoadFeed(feed_path);
  if (feed.empty()) { std::fprintf(stderr, "empty feed\n"); return 2; }

  aether_sfm_options_t opt;
  pwofficial_options_default(&opt);
  opt.max_features = 13312;          // researchMaxFeatures
  opt.image_width = static_cast<int>(feed[0].w);
  opt.image_height = static_cast<int>(feed[0].h);
  opt.match_max_ratio = 0.8f;        // defaultMatchMaxRatio
  opt.k_neighbors = 12;              // researchKNeighbors
  opt.use_gpu_match = gpu_match;     // 产品 1
  opt.use_gpu_extract = gpu_extract; // 产品 1
  std::printf("DRIVER feed=%s n=%zu max_features=%d k=%d ratio=%.3f gpu_match=%d gpu_extract=%d size=%dx%d\n",
              feed_path.c_str(), feed.size(), opt.max_features, opt.k_neighbors, opt.match_max_ratio,
              opt.use_gpu_match, opt.use_gpu_extract, opt.image_width, opt.image_height);
  std::fflush(stdout);

  const std::string sess_db = out_dir + "/session.db";
  std::remove(sess_db.c_str());
  aether_sfm_session_t* s = nullptr;
  aether_sfm_result_t rc = pwofficial_create(sess_db.c_str(), &opt, &s);
  if (rc != AETHER_SFM_OK || !s) {
    std::fprintf(stderr, "pwofficial_create failed: %s\n", ResultStr(rc));
    return 2;
  }

  std::FILE* per_frame = std::fopen((out_dir + "/per_frame.jsonl").c_str(), "w");
  int fed = 0, rejected = 0;
  const double t_stream0 = NowMs();
  for (const Feed& f : feed) {
    int out_fid = -1;
    const double t0 = NowMs();
    rc = AddJpegFrameV2AnySize(s, f.jpeg.c_str(), f.ts, static_cast<float>(f.k[0]),
                                      static_cast<float>(f.k[1]), static_cast<float>(f.k[2]),
                                      static_cast<float>(f.k[3]), f.q, f.t, f.trusted ? 1 : 0, &out_fid);
    const double add_ms = NowMs() - t0;
    double ex_ms = 0, mt_ms = 0;
    int n_cand = 0, gm = 0, cm = 0;
    pwofficial_debug_last(s, &ex_ms, &mt_ms, &n_cand, &gm, &cm);
    std::fprintf(per_frame,
                 "{\"frameIndex\":%lld,\"trusted\":%d,\"rc\":\"%s\",\"fid\":%d,\"add_ms\":%.1f,"
                 "\"extract_ms\":%.1f,\"match_ms\":%.1f,\"n_cand\":%d,\"gpu_matches\":%d,\"cpu_matches\":%d}\n",
                 f.frame_index, f.trusted ? 1 : 0, ResultStr(rc), out_fid, add_ms, ex_ms, mt_ms, n_cand, gm, cm);
    std::fflush(per_frame);
    if (rc != AETHER_SFM_OK) {
      ++rejected;
      std::fprintf(stderr, "frame %lld: add failed: %s\n", f.frame_index, ResultStr(rc));
      continue;
    }
    ++fed;
    std::printf("  fed %d/%zu frame=%lld fid=%d trusted=%d add_ms=%.0f extract_ms=%.0f cand=%d\n", fed,
                feed.size(), f.frame_index, out_fid, f.trusted ? 1 : 0, add_ms, ex_ms, n_cand);
    std::fflush(stdout);
  }
  std::fclose(per_frame);
  const double stream_ms = NowMs() - t_stream0;

  int64_t tvg = 0, raw = 0, ga = 0, gr = 0, rf = 0, tf = 0, x[31] = {0};
  pwofficial_stream_stats(s, &tvg, &raw, &ga, &gr, &rf, &tf, &x[0], &x[1], &x[2], &x[3], &x[4], &x[5],
                          &x[6], &x[7], &x[8], &x[9], &x[10], &x[11], &x[12], &x[13], &x[14], &x[15], &x[16],
                          &x[17], &x[18], &x[19], &x[20], &x[21], &x[22], &x[23], &x[24], &x[25], &x[26],
                          &x[27], &x[28], &x[29]);
  int64_t sp_first = 0, temporal_fb = 0;
  pwofficial_candidate_stats(s, &sp_first, &temporal_fb);
  std::printf("STREAMED fed=%d rejected=%d stream_ms=%.1f tvg_pairs=%lld raw_pairs=%lld grow_acc=%lld "
              "grow_rej=%lld spatial_first=%lld temporal_fallback=%lld spatial_attempted=%lld "
              "spatial_written=%lld spatial_inliers=%lld\n",
              fed, rejected, stream_ms, (long long)tvg, (long long)raw, (long long)ga, (long long)gr,
              (long long)sp_first, (long long)temporal_fb, (long long)x[10], (long long)x[11],
              (long long)x[12]);
  std::fflush(stdout);

  char fj[4096] = {0};
  const double t_fin0 = NowMs();
  rc = pwofficial_finalize_async(s, fj, sizeof(fj));
  if (rc != AETHER_SFM_OK) {
    std::printf("RESULT finalize=ASYNC_FAILED rc=%s\n", ResultStr(rc));
    pwofficial_free(s);
    return 4;
  }
  std::printf("FINALIZE_ASYNC phase1=%s\n", fj);
  std::fflush(stdout);
  int status = pwofficial_finalize_status(s);
  while (status != 2 && status != 3) {
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    status = pwofficial_finalize_status(s);
  }
  const double finalize_ms = NowMs() - t_fin0;
  std::printf("FINALIZE status=%d finalize_ms=%.1f\n", status, finalize_ms);
  std::fflush(stdout);
  if (status == 3) {
    std::printf("RESULT finalize=ERROR fed=%d rejected=%d\n", fed, rejected);
    pwofficial_free(s);
    return 5;
  }
  {
    int64_t uf = 0, ur = 0, ec = 0, ef = 0, lr = 0, ud = 0;
    pwofficial_registration_evidence_stats_v1(s, &uf, &ur, &ec, &ef, &lr, &ud);
    std::printf("REG_EVIDENCE untrusted_fed=%lld untrusted_registered=%lld evidence_checked=%lld "
                "evidence_failed=%lld late_registered=%lld unregistered_delivered=%lld\n",
                (long long)uf, (long long)ur, (long long)ec, (long long)ef, (long long)lr, (long long)ud);
  }
  std::vector<aether_sfm_pose_t> poses(feed.size() + 8);
  int n_pose = 0;
  pwofficial_get_poses(s, poses.data(), static_cast<int>(poses.size()), &n_pose);
  int n_reg = 0;
  std::FILE* pf = std::fopen((out_dir + "/delivered_poses.txt").c_str(), "w");
  for (int i = 0; i < n_pose; ++i) {
    if (poses[i].registered) ++n_reg;
    const int fid = poses[i].frame_id;
    const long long fi = (fid >= 0 && fid < static_cast<int>(feed.size())) ? feed[fid].frame_index : -1;
    std::fprintf(pf, "%d %lld %d %.17g %.17g %.17g %.17g %.17g %.17g %.17g\n", fid, fi, poses[i].registered,
                 poses[i].qwxyz[0], poses[i].qwxyz[1], poses[i].qwxyz[2], poses[i].qwxyz[3], poses[i].t[0],
                 poses[i].t[1], poses[i].t[2]);
  }
  std::fclose(pf);
  // 带观测的点(一次快照):点 xyz + 每条观测 (frame_id, x, y),写成纯文本供离线算重投影误差
  aether_sfm_point_t* tp = nullptr;
  int n_tp = 0;
  int32_t* offs = nullptr;
  aether_sfm_track_obs_t* obs = nullptr;
  int64_t n_obs = 0;
  if (pwofficial_get_points_tracked(s, &tp, &n_tp, &offs, &obs, &n_obs) == AETHER_SFM_OK) {
    std::FILE* tf2 = std::fopen((out_dir + "/tracks.txt").c_str(), "w");
    for (int i = 0; i < n_tp; ++i) {
      std::fprintf(tf2, "P %.9g %.9g %.9g %d\n", tp[i].x, tp[i].y, tp[i].z, offs[i + 1] - offs[i]);
      for (int j = offs[i]; j < offs[i + 1]; ++j)
        std::fprintf(tf2, "%d %.4f %.4f\n", obs[j].frame_id, obs[j].x, obs[j].y);
    }
    std::fclose(tf2);
    WritePly(out_dir + "/cloud.ply", tp, n_tp);
    pwofficial_points_free(tp);
    pwofficial_track_obs_free(offs, obs);
  }
  std::printf("RESULT finalize=REFINED fed=%d rejected=%d n_reg=%d/%d cloud_points=%d n_obs=%lld "
              "stream_ms=%.1f finalize_ms=%.1f total_ms=%.1f\n",
              fed, rejected, n_reg, n_pose, n_tp, (long long)n_obs, stream_ms, finalize_ms,
              stream_ms + finalize_ms);
  std::fflush(stdout);
  pwofficial_free(s);
  return 0;
}
