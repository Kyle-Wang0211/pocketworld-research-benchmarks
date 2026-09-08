// M2/M3 CPU reference: CLAHE(6.0,8x8) -> buildOpticalFlowPyramid(21x21,3,deriv) -> GFTT(150,1e-3,20,3,harris) -> LK fwd/back.
// Mirrors xrslam-extra/opencv_image.cpp (preprocess / detect_keypoints / track_keypoints). Gate build = OpenCV 4.0.1.
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/video.hpp>
#include <opencv2/features2d.hpp>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>
using namespace cv;
static Mat readU8(const char* p, int w, int h) { Mat m(h, w, CV_8UC1); FILE* f = fopen(p, "rb"); if (!f || fread(m.data, 1, (size_t)w * h, f) != (size_t)w * h) { fprintf(stderr, "read %s failed\n", p); exit(2); } fclose(f); return m; }
static void dump(const std::string& p, const Mat& m) { Mat c = m.isContinuous() ? m : m.clone(); FILE* f = fopen(p.c_str(), "wb"); fwrite(c.data, 1, c.total() * c.elemSize(), f); fclose(f); }
static Mat padded(const Mat& roi) { Size full; Point ofs; roi.locateROI(full, ofs); Mat m = roi; m.adjustROI(ofs.y, full.height - ofs.y - roi.rows, ofs.x, full.width - ofs.x - roi.cols); return m; }
int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "usage: W H prev.u8 outdir [next.u8]\n"); return 1; }
    int W = atoi(argv[1]), H = atoi(argv[2]); std::string out = argv[4];
    Mat prev = readU8(argv[3], W, H), next;
    if (argc > 5) next = readU8(argv[5], W, H);
    else { double th = 0.5 * CV_PI / 180.0, c = cos(th), s = sin(th), cx = W / 2.0, cy = H / 2.0; Mat M = (Mat_<double>(2, 3) << c, s, (1 - c) * cx - s * cy + 3.2, -s, c, s * cx + (1 - c) * cy - 2.1); warpAffine(prev, next, M, prev.size(), INTER_LINEAR, BORDER_REFLECT_101); dump(out + "/next_raw.u8", next); }
    Ptr<CLAHE> clahe = createCLAHE(6.0, Size(8, 8));
    Mat pc, nc; clahe->apply(prev, pc); clahe->apply(next, nc);
    dump(out + "/prev_clahe.u8", pc); dump(out + "/next_clahe.u8", nc);
    std::vector<Mat> pp, np;
    int lp = buildOpticalFlowPyramid(pc, pp, Size(21, 21), 3, true);
    int ln = buildOpticalFlowPyramid(nc, np, Size(21, 21), 3, true);
    printf("levels prev=%d next=%d pyr.size=%zu\n", lp, ln, pp.size());
    for (int l = 0; l <= lp; l++) {
        Mat im = pp[2 * l], dv = pp[2 * l + 1], imp = padded(im), dvp = padded(dv);
        printf("L%d %dx%d pad %dx%d | deriv type=%d %dx%d pad %dx%d\n", l, im.cols, im.rows, imp.cols, imp.rows, dv.type(), dv.cols, dv.rows, dvp.cols, dvp.rows);
        char b[64];
        snprintf(b, 64, "/prev_L%d.u8", l); dump(out + b, im); snprintf(b, 64, "/prev_L%d_pad.u8", l); dump(out + b, imp);
        snprintf(b, 64, "/prev_D%d.i16x2", l); dump(out + b, dv); snprintf(b, 64, "/prev_D%d_pad.i16x2", l); dump(out + b, dvp);
        snprintf(b, 64, "/next_L%d.u8", l); dump(out + b, np[2 * l]); snprintf(b, 64, "/next_L%d_pad.u8", l); dump(out + b, padded(np[2 * l]));
        snprintf(b, 64, "/next_D%d_pad.i16x2", l); dump(out + b, padded(np[2 * l + 1]));
    }
    std::vector<KeyPoint> kps; GFTTDetector::create(150, 1.0e-3, 20, 3, true)->detect(pc, kps);
    std::sort(kps.begin(), kps.end(), [](const KeyPoint& a, const KeyPoint& b) { return a.response > b.response; });
    std::vector<Point2f> p0; for (auto& k : kps) p0.push_back(k.pt);
    { std::ofstream f(out + "/gftt_clahe.txt"); f.precision(9); for (auto& k : kps) f << k.pt.x << " " << k.pt.y << " " << k.response << "\n"; }
    TermCriteria tc(TermCriteria::COUNT + TermCriteria::EPS, 30, 0.01);
    std::vector<Point2f> p1 = p0; std::vector<uchar> st; std::vector<float> err;
    calcOpticalFlowPyrLK(pp, np, p0, p1, st, err, Size(21, 21), 3, tc, OPTFLOW_USE_INITIAL_FLOW);
    std::vector<Point2f> pr = p0; std::vector<uchar> str; std::vector<float> errr;
    calcOpticalFlowPyrLK(np, pp, p1, pr, str, errr, Size(21, 21), 3, tc, OPTFLOW_USE_INITIAL_FLOW);
    int ok = 0; { std::ofstream f(out + "/lk_cpu.txt"); f.precision(9);
        for (size_t i = 0; i < p0.size(); i++) { f << p0[i].x << " " << p0[i].y << " " << p1[i].x << " " << p1[i].y << " " << int(st[i]) << " " << err[i] << " " << pr[i].x << " " << pr[i].y << " " << int(str[i]) << "\n"; ok += st[i]; } }
    printf("gftt=%zu lk_ok=%d  (OpenCV %s)\n", kps.size(), ok, CV_VERSION);
    return 0;
}
