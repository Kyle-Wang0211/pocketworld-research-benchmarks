// luma_to_jpeg.c — [offline_sfm 2026-09-25] 录制 frames.bin(luma8,1920x1440,
// recording_manifest.json "luma8_from_420f_full_range")里指定帧 → JPEG。
// 编码设置照抄产品 OfficialAetherARKitPlugin.swift encodeCVPixelBufferAsJpeg
// (pocketworld 3f28853:2776-2811):ImageIO CGImageDestination "public.jpeg",
// kCGImageDestinationLossyCompressionQuality = 0.92(capture_session.dart:1449
// ARFrameSaveSpec quality: 0.92),kCGImagePropertyOrientation = .right(6),
// 像素保持传感器横向。与产品唯一的差别:录制只有亮度平面,所以这里编的是
// 单通道灰度 JPEG(产品是 CIImage→RGB→JPEG;核只取 JPEG 的亮度平面)。
// 用法:luma_to_jpeg <frames.bin> <W> <H> <out_dir> <frame_index>...
//       输出 <out_dir>/f<frame_index 6 位>.jpg;逐帧打印 sha256 前缀不做,交给 shasum。
#include <CoreFoundation/CoreFoundation.h>
#include <CoreGraphics/CoreGraphics.h>
#include <ImageIO/ImageIO.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char** argv) {
  if (argc < 6) {
    fprintf(stderr, "usage: %s <frames.bin> <W> <H> <out_dir> <idx>...\n", argv[0]);
    return 1;
  }
  const char* bin = argv[1];
  const long W = atol(argv[2]), H = atol(argv[3]);
  const char* out_dir = argv[4];
  FILE* f = fopen(bin, "rb");
  if (!f) { fprintf(stderr, "cannot open %s\n", bin); return 2; }
  const size_t n = (size_t)W * (size_t)H;
  unsigned char* buf = (unsigned char*)malloc(n);
  CGColorSpaceRef gray = CGColorSpaceCreateDeviceGray();
  const float quality = 0.92f;
  const int orientation = 6;  // CGImagePropertyOrientation.right
  CFNumberRef q = CFNumberCreate(NULL, kCFNumberFloatType, &quality);
  CFNumberRef o = CFNumberCreate(NULL, kCFNumberIntType, &orientation);
  const void* keys[2] = {kCGImageDestinationLossyCompressionQuality, kCGImagePropertyOrientation};
  const void* vals[2] = {q, o};
  CFDictionaryRef opts = CFDictionaryCreate(NULL, keys, vals, 2, &kCFTypeDictionaryKeyCallBacks,
                                            &kCFTypeDictionaryValueCallBacks);
  for (int a = 5; a < argc; ++a) {
    const long idx = atol(argv[a]);
    if (fseeko(f, (off_t)idx * (off_t)n, SEEK_SET) != 0 || fread(buf, 1, n, f) != n) {
      fprintf(stderr, "short read frame %ld\n", idx);
      return 3;
    }
    CFDataRef data = CFDataCreate(NULL, buf, (CFIndex)n);
    CGDataProviderRef prov = CGDataProviderCreateWithCFData(data);
    CGImageRef img = CGImageCreate(W, H, 8, 8, W, gray, kCGImageAlphaNone, prov, NULL, false,
                                   kCGRenderingIntentDefault);
    char path[4096];
    snprintf(path, sizeof(path), "%s/f%06ld.jpg", out_dir, idx);
    CFURLRef url = CFURLCreateFromFileSystemRepresentation(NULL, (const UInt8*)path, strlen(path), false);
    CGImageDestinationRef dest = CGImageDestinationCreateWithURL(url, CFSTR("public.jpeg"), 1, NULL);
    if (!dest) { fprintf(stderr, "dest failed %s\n", path); return 4; }
    CGImageDestinationAddImage(dest, img, opts);
    if (!CGImageDestinationFinalize(dest)) { fprintf(stderr, "finalize failed %s\n", path); return 5; }
    CFRelease(dest); CFRelease(url); CGImageRelease(img); CGDataProviderRelease(prov); CFRelease(data);
    printf("%s\n", path);
  }
  CFRelease(opts); CFRelease(q); CFRelease(o); CGColorSpaceRelease(gray);
  free(buf);
  fclose(f);
  return 0;
}
