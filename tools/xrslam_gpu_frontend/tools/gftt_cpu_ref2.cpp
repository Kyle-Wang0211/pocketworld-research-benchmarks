// GFTT reference (OpenCV 4.0.1 build): raw u8 in -> img.u8, eig.f32 (cornerHarris 3/3/0.04), corners_cpu.txt (x y eig) as
// goodFeaturesToTrack(maxCorners, 1e-3, minDist 20, block 3, harris, 0.04) returns them, plus gftt_detector.txt via GFTTDetector.
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/features2d.hpp>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>
int main(int argc, char** argv) {
  if (argc < 6) { fprintf(stderr, "usage: gftt_cpu_ref2 <img.u8> W H <outdir> <maxCorners>\n"); return 1; }
  int W = atoi(argv[2]), H = atoi(argv[3]), maxC = atoi(argv[5]); std::string out = argv[4];
  cv::Mat img(H, W, CV_8UC1); FILE* f = fopen(argv[1], "rb"); if (!f || fread(img.data, 1, (size_t)W * H, f) != (size_t)W * H) { fprintf(stderr, "read fail\n"); return 2; } fclose(f);
  cv::Mat eig; cv::cornerHarris(img, eig, 3, 3, 0.04);
  { double scale = (double)(1 << (3 - 1)) * 3 * 255.0; scale = 1.0 / scale; cv::Mat Dx, Dy; cv::Sobel(img, Dx, CV_32F, 1, 0, 3, scale, 0, cv::BORDER_DEFAULT); cv::Sobel(img, Dy, CV_32F, 0, 1, 3, scale, 0, cv::BORDER_DEFAULT);
    FILE* g = fopen((out + "/dx.f32").c_str(), "wb"); fwrite(Dx.data, 4, (size_t)W * H, g); fclose(g); g = fopen((out + "/dy.f32").c_str(), "wb"); fwrite(Dy.data, 4, (size_t)W * H, g); fclose(g); }
  std::vector<cv::Point2f> c; cv::goodFeaturesToTrack(img, c, maxC, 1.0e-3, 20, cv::noArray(), 3, true, 0.04);
  { FILE* g = fopen((out + "/img.u8").c_str(), "wb"); fwrite(img.data, 1, (size_t)W * H, g); fclose(g); }
  { FILE* g = fopen((out + "/eig.f32").c_str(), "wb"); fwrite(eig.data, 4, (size_t)W * H, g); fclose(g); }
  { std::ofstream o(out + "/corners_cpu.txt"); o.precision(9); for (auto& p : c) o << (int)p.x << " " << (int)p.y << " " << eig.at<float>((int)p.y, (int)p.x) << "\n"; }
  std::vector<cv::KeyPoint> k; cv::GFTTDetector::create(maxC, 1.0e-3, 20, 3, true)->detect(img, k);
  { std::ofstream o(out + "/gftt_detector.txt"); o.precision(9); for (auto& p : k) o << (int)p.pt.x << " " << (int)p.pt.y << " " << p.response << "\n"; }
  double mx; cv::minMaxLoc(eig, nullptr, &mx); printf("corners=%zu detector=%zu maxEig=%.9g (OpenCV %s)\n", c.size(), k.size(), mx, CV_VERSION); return 0;
}
