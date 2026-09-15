// dense_bench_main.cc — on-device end-to-end run of dense_pipeline from RAW capture inputs (poses, sparse points,
// photos). Two modes:
//   parity : refs [a,b] with the reference run's own noise and depths (parity stats)        dense_bench <bundle> <docs> a-b
//   box    : the viewer's selection box (bundle/box.txt: c s rot9), generated noise, whole subset; afterwards the
//            written PLY is read back and every point is checked against the box              dense_bench <bundle> <docs> box
#include "dense_pipeline.h"

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <vector>
#if defined(__APPLE__)
#include <mach/mach.h>
static size_t mem_now() { task_vm_info_data_t i; mach_msg_type_number_t c = TASK_VM_INFO_COUNT; return task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&i, &c) == KERN_SUCCESS ? (size_t)i.phys_footprint : 0; }
#else
static size_t mem_now() { return 0; }
#endif
using namespace aether::dense;

template <class T> static std::vector<T> read_vec(const std::string& p) {
    FILE* f = std::fopen(p.c_str(), "rb"); if (!f) { std::fprintf(stderr, "MISSING %s\n", p.c_str()); std::exit(2); }
    std::fseek(f, 0, SEEK_END); const long n = std::ftell(f); std::fseek(f, 0, SEEK_SET);
    std::vector<T> v((size_t)n / sizeof(T)); if (std::fread(v.data(), sizeof(T), v.size(), f) != v.size()) { std::exit(2); } std::fclose(f); return v;
}
static std::chrono::steady_clock::time_point T0;
static int on_progress(const char* phase, int done, int total, void*) {
    static std::string last;
    if (phase != last || done == total || done % 5 == 0 || done == 0) {
        std::printf("[%7.1fs] %s %d/%d\n", std::chrono::duration<double>(std::chrono::steady_clock::now() - T0).count(), phase, done, total); std::fflush(stdout);
        last = phase;
    }
    return 0;
}

int main(int argc, char** argv) {
    if (argc < 3) { std::fprintf(stderr, "usage: dense_bench <bundle_dir> <docs_dir> [a-b | box]\n"); return 1; }
    const std::string B = argv[1], docs = argv[2]; const std::string mode = argc > 3 ? argv[3] : "0-7";
    T0 = std::chrono::steady_clock::now();
    std::atomic<size_t> peak{0}; std::atomic<bool> stop{false};
    std::thread sampler([&] { while (!stop.load()) { size_t m = mem_now(), p = peak.load(); while (m > p && !peak.compare_exchange_weak(p, m)) {} std::this_thread::sleep_for(std::chrono::milliseconds(20)); } });

    DenseJob job;
    auto F = read_vec<double>(B + "/session_pack/frames.f64"); job.points = read_vec<float>(B + "/session_pack/points.f32");
    std::vector<std::string> names; { std::ifstream f(B + "/session_pack/names.txt"); std::string l; while (std::getline(f, l)) if (!l.empty()) names.push_back(l); }
    const int NF = (int)(F.size() / 14);
    for (int i = 0; i < NF; ++i) {
        const double* r = &F[(size_t)i * 14]; SessionFrame s;
        s.frame_id = r[0]; s.fx = r[1]; s.fy = r[2]; s.cx = r[3]; s.cy = r[4]; s.image_w = r[5]; s.image_h = r[6];
        for (int k = 0; k < 4; ++k) s.q[k] = r[7 + k]; for (int k = 0; k < 3; ++k) s.t[k] = r[11 + k];
        job.frames.push_back(s); job.jpeg_paths.push_back(B + "/photos/" + names[i]);
    }
    job.model_path = B + "/casdiffmvs_abep2.onnx"; job.webgpu = true;
    job.work_dir = docs + "/dense_work"; job.out_ply = docs + "/dense.ply";
    std::vector<float> noise, refd;
    const bool boxmode = mode == "box";
    if (boxmode) {
        FILE* f = std::fopen((B + "/box.txt").c_str(), "r"); if (!f) { std::fprintf(stderr, "MISSING box.txt\n"); return 2; }
        double v[15]; for (int k = 0; k < 15; ++k) if (std::fscanf(f, "%lf", &v[k]) != 1) return 2; std::fclose(f);
        job.has_box = true; for (int k = 0; k < 3; ++k) { job.box_c[k] = v[k]; job.box_s[k] = v[3 + k]; } for (int k = 0; k < 9; ++k) job.box_rot[k] = v[6 + k];
        job.ref_begin = 0; job.ref_end = -1;   // whole subset, generated noise (product path)
        std::printf("job: NF=%d points=%zu BOX c=(%.3f %.3f %.3f) s=(%.3f %.3f %.3f)\n", NF, job.points.size() / 3, v[0], v[1], v[2], v[3], v[4], v[5]);
    } else {
        int a = 0, b = 7; std::sscanf(mode.c_str(), "%d-%d", &a, &b);
        noise = read_vec<float>(B + "/noise.f32"); refd = read_vec<float>(B + "/refdepth.f32");
        job.ref_begin = a; job.ref_end = b; job.ext_noise = noise.data(); job.ref_depth = refd.data();
        std::printf("job: NF=%d points=%zu refs %d-%d noise %zu refdepth %zu\n", NF, job.points.size() / 3, a, b, noise.size(), refd.size());
    }
    std::fflush(stdout);

    DenseStats st; const int rc = dense_run(job, on_progress, nullptr, &st);
    stop.store(true); sampler.join();
    std::printf("\n══ dense_run rc=%d %s ══\n", rc, st.error.c_str());
    std::printf("  frames %d selected %d%s | session %.0f ms | images %d in %.0f ms | ORT session %.0f ms | inferred %d views: median %.1f ms, total %.1f s | fuse %.0f ms\n",
                st.NF, st.frames_selected, st.box_fallback ? " (fallback: all)" : "", st.session_ms, st.images, st.images_ms, st.ort_session_ms, st.inferred, st.infer_ms_median, st.infer_ms_total / 1000.0, st.fuse_ms);
    std::printf("  peak memory %.0f MB [phys_footprint]\n", peak.load() / 1e6);
    if (!boxmode)
        std::printf("  depth parity vs host reference (%d views): non-finite %zu, >1%% pixels %.4f%%, worst rel %.3f%%  ⇒ %s\n", st.inferred, st.parity_nonfinite,
                    100.0 * st.parity_bad1 / std::max<size_t>(st.parity_pixels, 1), 100.0 * st.parity_worst_rel,
                    (st.parity_nonfinite == 0 && 100.0 * st.parity_bad1 / std::max<size_t>(st.parity_pixels, 1) < 0.1) ? "✅" : "🔴");
    std::printf("  fusion: frames %d points %zu photo %.2f%% geo %.2f%% final %.2f%%  HALL %016llx\n", st.fuse.frames, st.fuse.points,
                100 * st.fuse.photo_frac, 100 * st.fuse.geo_frac, 100 * st.fuse.final_frac, (unsigned long long)st.fuse.digest);
    if (boxmode && rc == 0) {   // read the PLY back: every delivered point must satisfy the box
        BoxFilter box{}; for (int k = 0; k < 3; ++k) { box.c[k] = job.box_c[k]; box.s[k] = job.box_s[k]; } for (int k = 0; k < 9; ++k) box.rot[k] = job.box_rot[k];
        FILE* f = std::fopen(job.out_ply.c_str(), "rb"); size_t n = 0, outside = 0;
        if (f) {
            char line[256]; long hdr = 0; size_t nv = 0;
            while (std::fgets(line, sizeof line, f)) { if (std::sscanf(line, "element vertex %zu", &nv) == 1) {} hdr = std::ftell(f); if (std::strncmp(line, "end_header", 10) == 0) break; }
            std::fseek(f, hdr, SEEK_SET);
            for (size_t i = 0; i < nv; ++i) { float p[3]; uint8_t c[3]; if (std::fread(p, 4, 3, f) != 3 || std::fread(c, 1, 3, f) != 3) break; ++n; if (!box.contains(p[0], p[1], p[2])) ++outside; }
            std::fclose(f);
        }
        std::printf("  PLY read-back: %zu points, outside box %zu  ⇒ %s\n", n, outside, (n == st.fuse.points && outside == 0) ? "✅" : "🔴");
    }
    for (size_t i = 0; i < st.fuse.frame_digest.size() && i < 8; ++i) std::printf("  H %04zu %016llx\n", i, (unsigned long long)st.fuse.frame_digest[i]);
    return rc;
}
