// Does calcOpticalFlowPyrLK give identical results with a derivative-free pyramid (on-the-fly Scharr) vs a withDerivatives pyramid? OpenCV 4.0.1.
#include <opencv2/video.hpp>
#include <opencv2/imgproc.hpp>
#include <cstdio>
#include <fstream>
#include <vector>
using namespace cv;
static std::vector<uchar> rd(const std::string& p, size_t n) { std::vector<uchar> v(n); FILE* f = fopen(p.c_str(), "rb"); if (!f) { fprintf(stderr, "open %s\n", p.c_str()); exit(1); } fread(v.data(), 1, n, f); fclose(f); return v; }
int main(int argc, char** argv) {
    std::string d = argv[1]; int W = atoi(argv[2]), H = atoi(argv[3]);
    auto a = rd(d + "/prev_clahe.u8", (size_t)W * H), b = rd(d + "/next_clahe.u8", (size_t)W * H);
    Mat pc(H, W, CV_8U, a.data()), nc(H, W, CV_8U, b.data());
    std::vector<Mat> pd, nd, pn, nn;
    buildOpticalFlowPyramid(pc, pd, Size(21, 21), 3, true); buildOpticalFlowPyramid(nc, nd, Size(21, 21), 3, true);
    buildOpticalFlowPyramid(pc, pn, Size(21, 21), 3, false); buildOpticalFlowPyramid(nc, nn, Size(21, 21), 3, false);
    std::vector<Point2f> p0; { std::ifstream f(d + "/lk_cpu.txt"); float ax, ay, bx, by, e, cx, cy; int s, sr; while (f >> ax >> ay >> bx >> by >> s >> e >> cx >> cy >> sr) p0.push_back(Point2f(ax, ay)); }
    TermCriteria tc(TermCriteria::COUNT + TermCriteria::EPS, 30, 0.01);
    std::vector<Point2f> p1 = p0, p2 = p0; std::vector<uchar> s1, s2; std::vector<float> e1, e2;
    calcOpticalFlowPyrLK(pd, nd, p0, p1, s1, e1, Size(21, 21), 3, tc, OPTFLOW_USE_INITIAL_FLOW);
    calcOpticalFlowPyrLK(pn, nn, p0, p2, s2, e2, Size(21, 21), 3, tc, OPTFLOW_USE_INITIAL_FLOW);
    size_t pos = 0, st = 0; double maxd = 0; for (size_t i = 0; i < p0.size(); ++i) { if ((s1[i] != 0) != (s2[i] != 0)) ++st; if (s1[i] && s2[i] && (p1[i] != p2[i])) { ++pos; maxd = std::max(maxd, (double)std::max(fabs(p1[i].x - p2[i].x), fabs(p1[i].y - p2[i].y))); if (pos <= 2) printf("  i=%zu deriv=(%.6f,%.6f) nod=(%.6f,%.6f)\n", i, p1[i].x, p1[i].y, p2[i].x, p2[i].y); } }
    printf("points=%zu pos_diff=%zu status_diff=%zu maxdiff=%g\n", p0.size(), pos, st, maxd);
    // variant: derivative-free pyramid but with the SAME level Mats as the deriv pyramid (image entries only)
    std::vector<Mat> pn2{pd[0], pd[2], pd[4], pd[6]}, nn2{nd[0], nd[2], nd[4], nd[6]}; std::vector<Point2f> p3 = p0; std::vector<uchar> s3; std::vector<float> e3;
    calcOpticalFlowPyrLK(pn2, nn2, p0, p3, s3, e3, Size(21, 21), 3, tc, OPTFLOW_USE_INITIAL_FLOW);
    size_t pos3 = 0; for (size_t i = 0; i < p0.size(); ++i) if (s1[i] && s3[i] && p1[i] != p3[i]) ++pos3; printf("same-levels-no-deriv vs deriv: pos_diff=%zu\n", pos3);
    return 0;
}
