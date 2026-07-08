#include "NativeBench.h"
#include <vector>
#include <cmath>
#include <random>
#include <chrono>
#include <thread>
#include <algorithm>

using clk = std::chrono::high_resolution_clock;
static double ms_since(clk::time_point t0) {
    return std::chrono::duration<double, std::milli>(clk::now() - t0).count();
}

int pw_num_cores(void) {
    int n = (int)std::thread::hardware_concurrency();
    return n > 0 ? n : 1;
}

// ---- matching: brute-force 128-d L2, nearest + Lowe ratio, multithreaded ----
static void match_range(const float *A, const float *B, int numDesc,
                        int i0, int i1, long *outSink) {
    const int D = 128;
    long sink = 0;
    for (int i = i0; i < i1; i++) {
        const float *a = &A[(size_t)i * D];
        float best = 1e30f, second = 1e30f; int bi = -1;
        for (int j = 0; j < numDesc; j++) {
            const float *b = &B[(size_t)j * D];
            float dist = 0;
            for (int d = 0; d < D; d++) { float df = a[d] - b[d]; dist += df * df; }
            if (dist < best)        { second = best; best = dist; bi = j; }
            else if (dist < second) second = dist;
        }
        if (best < 0.49f * second) sink += bi;   // ratio 0.7 -> 0.7^2 on squared L2
    }
    *outSink = sink;
}

double pw_bench_match(int numDesc, int numPairs, int threads) {
    const int D = 128;
    std::mt19937 rng(123);
    std::uniform_real_distribution<float> u(0.f, 1.f);
    std::vector<float> A((size_t)numDesc * D), B((size_t)numDesc * D);
    for (auto &x : A) x = u(rng);
    for (auto &x : B) x = u(rng);
    for (auto *V : {&A, &B})
        for (int i = 0; i < numDesc; i++) {
            float s = 0; for (int d = 0; d < D; d++) s += (*V)[i*D+d]*(*V)[i*D+d];
            s = std::sqrt(s) + 1e-9f;
            for (int d = 0; d < D; d++) (*V)[i*D+d] /= s;
        }
    int nt = threads > 0 ? threads : pw_num_cores();
    nt = std::max(1, std::min(nt, numDesc));

    auto t0 = clk::now();
    for (int p = 0; p < numPairs; p++) {
        std::vector<std::thread> pool;
        std::vector<long> sinks(nt, 0);
        int chunk = (numDesc + nt - 1) / nt;
        for (int t = 0; t < nt; t++) {
            int i0 = t * chunk, i1 = std::min(numDesc, i0 + chunk);
            if (i0 >= i1) break;
            pool.emplace_back(match_range, A.data(), B.data(), numDesc, i0, i1, &sinks[t]);
        }
        for (auto &th : pool) th.join();
    }
    return ms_since(t0);
}

// ---- extraction: representative Gaussian pyramid + DoG + descriptor sampling ----
static void blur_h(const std::vector<float>&src, std::vector<float>&dst, int w, int h, const float*k, int r){
    for (int y=0;y<h;y++) for (int x=0;x<w;x++){
        float s=0; for(int t=-r;t<=r;t++){int xx=std::min(w-1,std::max(0,x+t)); s+=src[(size_t)y*w+xx]*k[t+r];}
        dst[(size_t)y*w+x]=s;
    }
}
static void blur_v(const std::vector<float>&src, std::vector<float>&dst, int w, int h, const float*k, int r){
    for (int y=0;y<h;y++) for (int x=0;x<w;x++){
        float s=0; for(int t=-r;t<=r;t++){int yy=std::min(h-1,std::max(0,y+t)); s+=src[(size_t)yy*w+x]*k[t+r];}
        dst[(size_t)y*w+x]=s;
    }
}

double pw_bench_extract(int width, int height, int octaves, int threads) {
    (void)threads;                              // extraction here is single-image, single-thread (COLMAP threads across images)
    const int SCALES = 3;                        // DoG layers per octave (SIFT default ~3)
    const int r = 4; const float sigma = 1.6f;
    float k[2*4+1]; { float s=0; for(int t=-r;t<=r;t++){k[t+r]=std::exp(-(t*t)/(2*sigma*sigma)); s+=k[t+r];} for(auto&v:k)v/=s; }
    std::mt19937 rng(7); std::uniform_real_distribution<float> u(0.f,1.f);
    int w=width, h=height;
    std::vector<float> img((size_t)w*h); for(auto&x:img)x=u(rng);

    auto t0 = clk::now();
    volatile double sink = 0;
    for (int o = 0; o < octaves && w >= 16 && h >= 16; o++) {
        std::vector<float> cur=img, tmp((size_t)w*h), prev((size_t)w*h);
        for (int s = 0; s < SCALES + 1; s++) {
            blur_h(cur, tmp, w, h, k, r);
            blur_v(tmp, cur, w, h, k, r);        // Gaussian blur (separable)
            if (s > 0) {                          // DoG = difference of consecutive blurs
                for (size_t i=0;i<(size_t)w*h;i++){ float d=cur[i]-prev[i]; sink += d>0.02f?1.0:0.0; }
            }
            prev = cur;
        }
        // descriptor sampling proxy: 4x4x8 gradient histogram at ~2000 keypoints
        for (int kp=0; kp<2000; kp++){
            int x=4+(int)(u(rng)*(w-8)), y=4+(int)(u(rng)*(h-8)); float acc=0;
            for(int by=-2;by<2;by++) for(int bx=-2;bx<2;bx++){
                int xx=x+bx, yy=y+by; float gx=img[(size_t)yy*w+xx+1]-img[(size_t)yy*w+xx-1];
                float gy=img[(size_t)(yy+1)*w+xx]-img[(size_t)(yy-1)*w+xx];
                acc += std::sqrt(gx*gx+gy*gy);
            }
            sink += acc;
        }
        // downsample by 2 for next octave
        int nw=w/2, nh=h/2; std::vector<float> down((size_t)nw*nh);
        for(int y=0;y<nh;y++) for(int x=0;x<nw;x++) down[(size_t)y*nw+x]=img[(size_t)(2*y)*w+2*x];
        img.swap(down); w=nw; h=nh;
    }
    (void)sink;
    return ms_since(t0);
}
