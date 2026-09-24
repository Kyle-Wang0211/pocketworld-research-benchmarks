// gpu_vs_phone.cc — fixD batch checker (host only; inputs read-only).
// For each task line "<jpeg> <db> <image_id> <max_features>" on stdin:
//   1) decode the JPEG exactly like the phone (CGImage -> DeviceGray, no EXIF
//      rotation, kCGInterpolationNone; pwofficial_jpeg_decode.mm:48-110),
//   2) run the shipped GPU DSP-SIFT C ABI on the host GPU (Dawn/Metal) with the
//      production call shape (out_cap = max_features),
//   3) read the phone's stored keypoints for that image from the DB (sqlite
//      immutable=1, never written) and report the fraction of phone keypoints
//      that have a host keypoint within 0.05 px (and the reverse), plus scale
//      stats of both sets.
#include <CoreFoundation/CoreFoundation.h>
#include <CoreGraphics/CoreGraphics.h>
#include <ImageIO/ImageIO.h>
#include <sqlite3.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

extern "C" int aether_dsp_sift_extract_gpu_v2(
    const uint8_t*, int, int, int, int, float*, uint8_t*, float*, float*, int,
    int*);
extern "C" int aether_dsp_sift_extract_threaded_v2(
    const uint8_t*, int, int, int, int, float*, uint8_t*, float*, float*, int,
    int*) {
  std::fprintf(stderr, "CPU FALLBACK TAKEN\n");
  std::exit(7);
}
extern "C" int aether_dsp_sift_extract_threaded(const uint8_t*, int, int, int,
                                                int, float*, uint8_t*, int,
                                                int*) {
  std::fprintf(stderr, "CPU FALLBACK TAKEN\n");
  std::exit(7);
}

static bool DecodeCG(const char* path, std::vector<uint8_t>* gray, int* w,
                     int* h) {
  CFURLRef url = CFURLCreateFromFileSystemRepresentation(
      kCFAllocatorDefault, reinterpret_cast<const UInt8*>(path),
      static_cast<CFIndex>(std::strlen(path)), false);
  if (!url) return false;
  CGImageSourceRef src = CGImageSourceCreateWithURL(url, nullptr);
  CFRelease(url);
  if (!src) return false;
  CGImageRef img = CGImageSourceCreateImageAtIndex(src, 0, nullptr);
  CFRelease(src);
  if (!img) return false;
  const size_t W = CGImageGetWidth(img), H = CGImageGetHeight(img);
  gray->assign(W * H, 0);
  CGColorSpaceRef cs = CGColorSpaceCreateDeviceGray();
  CGContextRef ctx =
      CGBitmapContextCreate(gray->data(), W, H, 8, W, cs, kCGImageAlphaNone);
  CGColorSpaceRelease(cs);
  CGContextSetInterpolationQuality(ctx, kCGInterpolationNone);
  CGContextDrawImage(ctx, CGRectMake(0, 0, (CGFloat)W, (CGFloat)H), img);
  CGContextRelease(ctx);
  CGImageRelease(img);
  *w = (int)W;
  *h = (int)H;
  return true;
}

struct Grid {
  std::unordered_map<long long, std::vector<int>> cells;
  const float* xy;
  explicit Grid(const float* p, int n) : xy(p) {
    for (int i = 0; i < n; ++i)
      cells[key((int)std::floor(p[2 * i]), (int)std::floor(p[2 * i + 1]))]
          .push_back(i);
  }
  static long long key(int cx, int cy) {
    return ((long long)cx << 32) ^ (unsigned)cy;
  }
  bool near(float x, float y, float r) const {
    const int cx = (int)std::floor(x), cy = (int)std::floor(y);
    for (int dx = -1; dx <= 1; ++dx)
      for (int dy = -1; dy <= 1; ++dy) {
        auto it = cells.find(key(cx + dx, cy + dy));
        if (it == cells.end()) continue;
        for (int j : it->second) {
          const float ex = xy[2 * j] - x, ey = xy[2 * j + 1] - y;
          if (ex * ex + ey * ey <= r * r) return true;
        }
      }
    return false;
  }
};

static void stats(const std::vector<float>& s, double* med, double* flt3) {
  if (s.empty()) {
    *med = 0;
    *flt3 = 0;
    return;
  }
  std::vector<float> t = s;
  std::nth_element(t.begin(), t.begin() + t.size() / 2, t.end());
  *med = t[t.size() / 2];
  int c = 0;
  for (float v : s) c += v < 3.0f;
  *flt3 = (double)c / s.size();
}

int main() {
  std::string line;
  while (std::getline(std::cin, line)) {
    std::istringstream is(line);
    std::string jpeg, db, tag;
    int iid = 0, maxf = 0;
    is >> jpeg >> db >> iid >> maxf >> tag;
    std::vector<uint8_t> g;
    int W = 0, H = 0;
    if (!DecodeCG(jpeg.c_str(), &g, &W, &H)) {
      std::printf("%s ERR decode\n", tag.c_str());
      std::fflush(stdout);
      continue;
    }
    std::vector<float> xy(2 * (size_t)maxf), sc(maxf);
    std::vector<uint8_t> desc(128 * (size_t)maxf);
    int n = 0;
    const int rc = aether_dsp_sift_extract_gpu_v2(
        g.data(), W, H, maxf, 0, xy.data(), desc.data(), sc.data(), nullptr,
        maxf, &n);
    // phone keypoints
    sqlite3* h = nullptr;
    const std::string uri = "file:" + db + "?immutable=1";
    std::vector<float> pxy, ps;
    if (sqlite3_open_v2(uri.c_str(), &h, SQLITE_OPEN_READONLY | SQLITE_OPEN_URI,
                        nullptr) == SQLITE_OK) {
      sqlite3_stmt* st = nullptr;
      sqlite3_prepare_v2(
          h, "select rows,cols,data from keypoints where image_id=?", -1, &st,
          nullptr);
      sqlite3_bind_int(st, 1, iid);
      if (sqlite3_step(st) == SQLITE_ROW) {
        const int r = sqlite3_column_int(st, 0), c = sqlite3_column_int(st, 1);
        const float* a = (const float*)sqlite3_column_blob(st, 2);
        for (int i = 0; i < r && a; ++i) {
          pxy.push_back(a[i * c]);
          pxy.push_back(a[i * c + 1]);
          if (c == 6) {
            const float a11 = a[i * c + 2], a12 = a[i * c + 3],
                        a21 = a[i * c + 4], a22 = a[i * c + 5];
            ps.push_back(0.5f * (std::sqrt(a11 * a11 + a21 * a21) +
                                 std::sqrt(a12 * a12 + a22 * a22)));
          } else if (c == 4) {
            ps.push_back(a[i * c + 2]);
          }
        }
      }
      sqlite3_finalize(st);
      sqlite3_close(h);
    }
    const int pn = (int)pxy.size() / 2;
    Grid gh(xy.data(), n), gp(pxy.data(), pn);
    int m1 = 0, m2 = 0;
    for (int i = 0; i < pn; ++i) m1 += gh.near(pxy[2 * i], pxy[2 * i + 1], 0.05f);
    for (int i = 0; i < n; ++i) m2 += gp.near(xy[2 * i], xy[2 * i + 1], 0.05f);
    double hm, hf, pm, pf;
    stats(std::vector<float>(sc.begin(), sc.begin() + n), &hm, &hf);
    stats(ps, &pm, &pf);
    std::printf(
        "%s rc=%d host_n=%d phone_n=%d match_p2h=%.4f match_h2p=%.4f "
        "host_smed=%.2f host_flt3=%.3f phone_smed=%.2f phone_flt3=%.3f\n",
        tag.c_str(), rc, n, pn, pn ? (double)m1 / pn : 0.0,
        n ? (double)m2 / n : 0.0, hm, hf, pm, pf);
    std::fflush(stdout);
  }
  return 0;
}
