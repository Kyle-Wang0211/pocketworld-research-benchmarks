// cpu_extract.cc — fixD analysis tool (host only, read-only on inputs).
// Decodes one 12 MP phone JPEG exactly like the phone
// (pw-dense-stage vendor/official_sfm/src/pwofficial_jpeg_decode.mm:48-110,
// CGImage -> DeviceGray, kCGInterpolationNone, no EXIF rotation), or with
// libjpeg JCS_GRAYSCALE (step2 Mac replay driver), then runs the production CPU
// DSP-SIFT entry aether_dsp_sift_extract_v2 (official_dsp_sift_c.cc) with an
// out_cap large enough to see COLMAP's full output (whole (o,s) groups, the
// upstream CovariantSiftCPUFeatureExtractor semantics).
// Output binary: int32 n, then n*(x,y,scale,orient) float32, then n*128 u8.
// Also dumps the decoded gray image (for the GPU tool) when asked.
#include <CoreFoundation/CoreFoundation.h>
#include <CoreGraphics/CoreGraphics.h>
#include <ImageIO/ImageIO.h>
#include <jpeglib.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

extern "C" int aether_dsp_sift_extract_v2(const uint8_t* gray, int width,
                                          int height, int max_features,
                                          float* out_xy, uint8_t* out_desc,
                                          float* out_scales,
                                          float* out_orientations, int out_cap,
                                          int* out_count);

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
  CGContextRef ctx = CGBitmapContextCreate(gray->data(), W, H, 8, W, cs,
                                           kCGImageAlphaNone);
  CGColorSpaceRelease(cs);
  CGContextSetInterpolationQuality(ctx, kCGInterpolationNone);
  CGContextDrawImage(ctx, CGRectMake(0, 0, (CGFloat)W, (CGFloat)H), img);
  CGContextRelease(ctx);
  CGImageRelease(img);
  *w = (int)W;
  *h = (int)H;
  return true;
}

static bool DecodeLibjpeg(const char* path, std::vector<uint8_t>* gray, int* w,
                          int* h) {
  FILE* f = std::fopen(path, "rb");
  if (!f) return false;
  jpeg_decompress_struct cinfo;
  jpeg_error_mgr jerr;
  cinfo.err = jpeg_std_error(&jerr);
  jpeg_create_decompress(&cinfo);
  jpeg_stdio_src(&cinfo, f);
  jpeg_read_header(&cinfo, TRUE);
  cinfo.out_color_space = JCS_GRAYSCALE;
  jpeg_start_decompress(&cinfo);
  *w = cinfo.output_width;
  *h = cinfo.output_height;
  gray->assign((size_t)(*w) * (*h), 0);
  while (cinfo.output_scanline < cinfo.output_height) {
    JSAMPROW row = gray->data() + (size_t)cinfo.output_scanline * (*w);
    jpeg_read_scanlines(&cinfo, &row, 1);
  }
  jpeg_finish_decompress(&cinfo);
  jpeg_destroy_decompress(&cinfo);
  std::fclose(f);
  return true;
}

int main(int argc, char** argv) {
  if (argc < 5) {
    std::fprintf(stderr,
                 "usage: %s <cg|libjpeg> <jpeg> <max_features> <out.bin> "
                 "[gray_out.raw]\n",
                 argv[0]);
    return 2;
  }
  const std::string mode = argv[1];
  std::vector<uint8_t> gray;
  int w = 0, h = 0;
  bool ok = mode == "cg" ? DecodeCG(argv[2], &gray, &w, &h)
                         : DecodeLibjpeg(argv[2], &gray, &w, &h);
  if (!ok) {
    std::fprintf(stderr, "decode failed\n");
    return 3;
  }
  if (argc > 5) {
    FILE* g = std::fopen(argv[5], "wb");
    std::fwrite(gray.data(), 1, gray.size(), g);
    std::fclose(g);
  }
  const int maxf = std::atoi(argv[3]);
  const int cap = 400000;
  std::vector<float> xy(2 * (size_t)cap), sc(cap), orr(cap);
  std::vector<uint8_t> desc(128 * (size_t)cap);
  int n = 0;
  const int rc = aether_dsp_sift_extract_v2(gray.data(), w, h, maxf, xy.data(),
                                            desc.data(), sc.data(), orr.data(),
                                            cap, &n);
  std::printf("CPU_EXTRACT mode=%s %dx%d max_features=%d rc=%d n_full=%d\n",
              mode.c_str(), w, h, maxf, rc, n);
  FILE* o = std::fopen(argv[4], "wb");
  std::fwrite(&n, 4, 1, o);
  for (int i = 0; i < n; ++i) {
    float r[4] = {xy[2 * i], xy[2 * i + 1], sc[i], orr[i]};
    std::fwrite(r, 4, 4, o);
  }
  std::fwrite(desc.data(), 1, 128 * (size_t)n, o);
  std::fclose(o);
  return rc;
}
