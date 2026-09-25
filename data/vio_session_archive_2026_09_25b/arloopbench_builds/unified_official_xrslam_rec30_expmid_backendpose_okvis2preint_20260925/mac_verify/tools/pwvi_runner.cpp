// pwvi_runner.cpp -- S3 scratch tool (not for commit).
// [bkpose 2026-09-25] copy of scratchpad/wobble/tools/pwvi_runner.cpp (read-only there) +
//   --hex-out F     every fed frame: fed t, CAMERA_POSE (8 doubles), BODY_POSE (8 doubles), STATE as raw
//                   IEEE-754 bit patterns -> bit-exact before/after comparison by sha256
//   --keyed-out F   front-end CAMERA_POSE keyed by recording frame, same columns and same gate as the
//                   phone replay's poses_camera_by_recording_frame.csv (rc ok, TRACKING_SUCCESS,
//                   |q| >= 0.5, time strictly increasing)
//   --backend-out F (only when built with -DPW_BKPOSE_TAP) drain XRSLAMDrainBackendPoses after every
//                   RunOneFrame; after the last frame wait for the workers to go idle, drain again,
//                   then append the final window snapshot (kind 3). Recording frame / t_ns looked up
//                   by exact double equality of the fed timestamp.
// [dip13f 2026-09-25] + --drop-before-imu (phone: camera rows with t < first IMU are dropped),
//   + K counterfactuals on the per-frame K (full-res values, mapped with the same box-d formula):
//     --k-hold T0 T1       frames with raw t in [T0,T1] reuse the K of the last frame before T0
//     --k-const fx cx cy   every frame gets this K (fy=fx)
//     --k-scale T0 T1 f    fx,fy *= f inside [T0,T1]
// [xrofficial 2026-09-24] + --rate-hz R (production PwVioSlamFeeder admission rule on the raw
//   camera timestamp: drop if t - t_last_admitted < 1/R; = scaleS2 mk30.py), --pace P (feed at
//   P x real time, needed for the threaded arm), --camera-out (XRSLAM_RESULT_CAMERA_POSE rows).
//
// Same engine driving loop as pw_tools/regression/euroc_runner.cpp @04c0e83 (copied), but it can
// read a bench recording (run-*/frames.bin + camera_index.csv + imu.csv) DIRECTLY, so no 2.5 GB
// EuRoC/PNG conversion has to be written to a nearly-full disk.
//
// Bit-identity contract with the converter path (arloopbench/tools/pwvi_to_euroc.py -> EuRoC dir ->
// EurocDatasetReader):
//   * camera t  = strtod("<timestamp_ns>") * 1e-9 + cam0.time_offset   (euroc_dataset_reader.h:43-50,
//                                                                       euroc_dataset_reader.cpp:16-19)
//   * imu t     = strtod("<timestamp_ns>") * 1e-9, gyro and acc pushed at the same t
//   * event order: camera items first, then (gyro, acc) per imu row, then std::stable_sort by t
//     (euroc_dataset_reader.cpp:14-42)  => at equal t camera precedes imu, gyro precedes acc.
//   * pixels: raw luma8 rows. Converter --downscale d: numpy block mean + round (half-even);
//     sum/9 never lands on .5 so round == (sum + d*d/2) / (d*d) with integer division for odd d*d.
//     (d==1 -> bytes untouched; PNG round-trip is lossless for 8-bit gray.)
//   * frames with no index entry or wrong length are skipped (converter `missing`).
// Verified empirically against the EuRoC path before use (see S3 report).
//
//   pwvi_runner <slam.yaml> <device.yaml> (euroc://<dir> | pwvi://<run-dir>) <out.tum>
//               [--downscale d] [--intrinsics-jsonl]  (C arm: per-frame K from intrinsics.jsonl)

#include "dataset_reader.h"
#include <XRSLAM.h>
#include <xrslam/extra/yaml_config.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <map>
#include <thread>
#include <memory>
#include <sstream>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>
#include <cinttypes>
#ifdef PW_BKPOSE_TAP
#include <XRSLAMBackendPose.h>
#endif
extern "C" int XRSLAMGetPendingWorkerFrames(void);

namespace {

struct PoseRow {
    double t;
    double q[4];
    double p[3];
};

struct Ev {
    double t;
    int type; // 0 cam, 1 gyro, 2 acc
    size_t idx;
};

struct PwviData {
    std::vector<std::pair<double, size_t>> cams; // (t, byte offset)
    std::vector<long long> cam_fid;              // [bkpose] recording frame index (camera_index relative_path)
    std::vector<long long> cam_tns;              // [wobble] recording t_ns of each fed camera row
    std::vector<std::array<double, 4>> cam_k;    // per-frame K (C arm), NaN if none
    std::vector<std::array<double, 7>> imu;      // t, w, a
    std::vector<Ev> events;
    const uint8_t *base = nullptr;
    size_t map_len = 0;
    int W = 0, H = 0;
};

std::string slurp(const std::string &p) {
    std::ifstream f(p);
    if (!f) {
        fprintf(stderr, "cannot open %s\n", p.c_str());
        exit(1);
    }
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

long long json_int(const std::string &line, const char *key, bool *ok) {
    std::string k = std::string("\"") + key + "\":";
    size_t pos = line.find(k);
    if (pos == std::string::npos) {
        *ok = false;
        return 0;
    }
    *ok = true;
    return strtoll(line.c_str() + pos + k.size(), nullptr, 10);
}

double json_num(const std::string &line, const char *key, bool *ok) {
    std::string k = std::string("\"") + key + "\":";
    size_t pos = line.find(k);
    if (pos == std::string::npos) {
        *ok = false;
        return 0;
    }
    *ok = true;
    return strtod(line.c_str() + pos + k.size(), nullptr);
}

struct KMod {
    int kind; // 0 hold, 1 const, 2 scale
    double a, b, c, d;
};
std::vector<KMod> g_kmods;
bool g_drop_before_imu = false;
double g_td_extra = 0.0;   // [wobble] --td-extra-ms: added on top of the yaml c (+ exposure/2)
double g_cam_delay = 0.0;  // [preint] --cam-delay-ms:只改投递顺序(相机事件排序键 = t + D),喂进引擎的时间戳不变
double g_acc_shift = 0.0;  // [preint 诊断] --acc-shift-ms:加计时间戳整体平移(排序键与推给引擎的时间戳一起改),陀螺不动
std::string g_map_out;     // [wobble] --frame-map-out: "t_engine t_ns" per fed camera row
long g_limit_frames = 0; // [dip13f] phone -PWBenchReplayLimitFrames: camera_index row prefix

void load_pwvi(const std::string &dir, double time_offset, int ds, bool use_k, bool expo_half,
               double rate_hz, double rate_frac, PwviData &D) {
    double first_imu_t = -1e300;
    if (g_drop_before_imu) {
        std::ifstream f(dir + "/imu.csv");
        std::string ln;
        std::getline(f, ln);
        std::getline(f, ln);
        first_imu_t = strtod(ln.c_str(), nullptr) * 1e-9;
    }
    size_t n_pre_imu = 0;
    std::array<double, 4> k_hold_val = {NAN, NAN, NAN, NAN};
    std::array<double, 4> k_last_raw = {NAN, NAN, NAN, NAN};
    // manifest width/height
    std::string man = slurp(dir + "/recording_manifest.json");
    auto grab = [&](const char *key) {
        size_t p = man.find(std::string("\"") + key + "\"");
        p = man.find(':', p);
        return atoi(man.c_str() + p + 1);
    };
    D.W = grab("width");
    D.H = grab("height");
    const size_t expect = (size_t)D.W * D.H;
    // frames.pwvi
    std::map<long long, long long> off_by_frame;
    {
        std::ifstream f(dir + "/frames.pwvi");
        std::string ln;
        while (std::getline(f, ln)) {
            if (ln.empty())
                continue;
            bool ok1, ok2, ok3;
            long long fr = json_int(ln, "frame", &ok1);
            long long off = json_int(ln, "offset", &ok2);
            long long len = json_int(ln, "len", &ok3);
            if (!ok3)
                len = json_int(ln, "length", &ok3);
            if (!ok1 || !ok2 || !ok3) {
                fprintf(stderr, "bad pwvi line %s\n", ln.c_str());
                exit(1);
            }
            if ((size_t)len != expect) {
                fprintf(stderr, "frame %lld len %lld != %zu\n", fr, len, expect);
                exit(1);
            }
            off_by_frame[fr] = off;
        }
    }
    // intrinsics.jsonl (optional, C arm)
    std::vector<std::pair<long long, std::array<double, 4>>> krows;
    std::vector<std::pair<long long, double>> erows; // (t_ns, exposure_s)
    if (use_k || expo_half) {
        std::ifstream f(dir + "/intrinsics.jsonl");
        std::string ln;
        while (std::getline(f, ln)) {
            if (ln.empty())
                continue;
            bool ok;
            double t = json_num(ln, "t", &ok);
            if (!ok)
                continue;
            {
                bool oke;
                double e = json_num(ln, "exposure_s", &oke);
                if (oke && e >= 0)
                    erows.push_back({llround(t * 1e9), e});
            }
            size_t p = ln.find("\"intrinsics_fxfycxcy\":[");
            if (p == std::string::npos)
                continue;
            const char *c = ln.c_str() + p + strlen("\"intrinsics_fxfycxcy\":[");
            std::array<double, 4> k;
            char *e;
            for (int i = 0; i < 4; ++i) {
                k[i] = strtod(c, &e);
                c = e + 1;
            }
            krows.push_back({llround(t * 1e9), k});
        }
        std::sort(krows.begin(), krows.end(),
                  [](auto &a, auto &b) { return a.first < b.first; });
        std::sort(erows.begin(), erows.end(),
                  [](auto &a, auto &b) { return a.first < b.first; });
        if (expo_half && erows.empty()) {
            fprintf(stderr, "--exposure-half: no exposure_s in intrinsics.jsonl\n");
            exit(1);
        }
    }
    // camera_index.csv
    {
        std::ifstream f(dir + "/camera_index.csv");
        std::string ln;
        std::getline(f, ln); // header
        size_t n_missing = 0, n_kmiss = 0, n_rate_drop = 0;
        bool have_last_admit = false;
        double last_admit = 0.0;
        long n_rows = 0;
        while (std::getline(f, ln)) {
            if (ln.empty())
                continue;
            if (g_limit_frames > 0 && ++n_rows > g_limit_frames)
                break;
            size_t comma = ln.find(',');
            std::string ts = ln.substr(0, comma);
            long long fid = atoll(ln.c_str() + comma + 1);
            auto it = off_by_frame.find(fid);
            if (it == off_by_frame.end()) {
                ++n_missing;
                continue;
            }
            if (g_drop_before_imu && strtod(ts.c_str(), nullptr) * 1e-9 < first_imu_t) {
                ++n_pre_imu;
                continue;
            }
            if (rate_hz > 0) {
                // production PwVioSlamFeeder.enqueue(frame:): frame.timestamp - last < 1/R => drop
                const double t_raw = strtod(ts.c_str(), nullptr) * 1e-9;
                if (have_last_admit && t_raw - last_admit < rate_frac / rate_hz) {
                    ++n_rate_drop;
                    continue;
                }
                have_last_admit = true;
                last_admit = t_raw;
            }
            double t = strtod(ts.c_str(), nullptr) * 1e-9 + time_offset;
            if (expo_half) {
                // converter: t_out = t_ns + int(round(0.5*expo*1e9)) (nearest record, 1 ms tol)
                long long t_ns = atoll(ts.c_str());
                auto lb = std::lower_bound(erows.begin(), erows.end(), t_ns,
                                           [](const auto &r, long long v) { return r.first < v; });
                long long bestd = 1000001;
                double be = NAN;
                for (auto j : {lb == erows.begin() ? erows.end() : lb - 1, lb}) {
                    if (j == erows.end())
                        continue;
                    long long d = llabs(j->first - t_ns);
                    if (d <= 1000000 && d < bestd) {
                        bestd = d;
                        be = j->second;
                    }
                }
                if (std::isfinite(be)) {
                    long long t_out = t_ns + (long long)std::nearbyint(0.5 * be * 1e9);
                    t = strtod(std::to_string(t_out).c_str(), nullptr) * 1e-9 + time_offset;
                }
            }
            if (g_td_extra != 0.0) t += g_td_extra; // [wobble] extra relative td (s)
            D.cams.push_back({t, (size_t)it->second});
            D.cam_tns.push_back(atoll(ts.c_str()));
            D.cam_fid.push_back(fid);
            std::array<double, 4> kk = {NAN, NAN, NAN, NAN};
            if (use_k) {
                long long t_ns = atoll(ts.c_str());
                auto lb = std::lower_bound(
                    krows.begin(), krows.end(), t_ns,
                    [](const auto &r, long long v) { return r.first < v; });
                long long bestd = 1000001;
                const std::array<double, 4> *best = nullptr;
                for (auto j : {lb == krows.begin() ? krows.end() : lb - 1, lb}) {
                    if (j == krows.end())
                        continue;
                    long long d = llabs(j->first - t_ns);
                    if (d <= 1000000 && d < bestd) {
                        bestd = d;
                        best = &j->second;
                    }
                }
                if (best) {
                    double d = ds;
                    std::array<double, 4> raw = *best;
                    const double tr = strtod(ts.c_str(), nullptr) * 1e-9;
                    for (const KMod &km : g_kmods) {
                        if (km.kind == 1) {
                            raw = {km.a, km.a, km.b, km.c};
                        } else if (km.kind == 0 && tr >= km.a && tr <= km.b) {
                            if (!std::isfinite(k_hold_val[0]))
                                k_hold_val = std::isfinite(k_last_raw[0]) ? k_last_raw : raw;
                            raw = k_hold_val;
                        } else if (km.kind == 2 && tr >= km.a && tr <= km.b) {
                            raw[0] *= km.c;
                            raw[1] *= km.c;
                        }
                    }
                    if (!(g_kmods.size() && g_kmods[0].kind == 0 && tr >= g_kmods[0].a &&
                          tr <= g_kmods[0].b))
                        k_last_raw = *best;
                    kk = {raw[0] / d, raw[1] / d, (raw[2] + 0.5) / d - 0.5,
                          (raw[3] + 0.5) / d - 0.5};
                } else {
                    ++n_kmiss;
                }
            }
            D.cam_k.push_back(kk);
        }
        fprintf(stderr, "[pwvi] cams %zu (missing %zu, rate-dropped %zu @%.1f Hz, pre-imu dropped %zu) Kmiss %zu  W×H %d×%d ds %d kmods %zu\n",
                D.cams.size(), n_missing, n_rate_drop, rate_hz, n_pre_imu, n_kmiss, D.W, D.H, ds, g_kmods.size());
    }
    // imu.csv
    {
        std::ifstream f(dir + "/imu.csv");
        std::string ln;
        std::getline(f, ln);
        while (std::getline(f, ln)) {
            if (ln.empty())
                continue;
            std::array<double, 7> r;
            const char *c = ln.c_str();
            char *e;
            for (int i = 0; i < 7; ++i) {
                r[i] = strtod(c, &e);
                c = e + 1;
            }
            r[0] *= 1e-9;
            D.imu.push_back(r);
        }
    }
    for (size_t i = 0; i < D.cams.size(); ++i)
        D.events.push_back({D.cams[i].first + g_cam_delay, 0, i});
    for (size_t i = 0; i < D.imu.size(); ++i) {
        D.events.push_back({D.imu[i][0], 1, i});
        D.events.push_back({D.imu[i][0] + g_acc_shift, 2, i});
    }
    std::stable_sort(D.events.begin(), D.events.end(),
                     [](const Ev &a, const Ev &b) { return a.t < b.t; });
    // camera queue order == stable_sort of cams by t; verify monotone (it is, but check)
    for (size_t i = 1; i < D.cams.size(); ++i)
        if (D.cams[i].first < D.cams[i - 1].first) {
            fprintf(stderr, "camera times not monotone; stable-sort semantics differ\n");
            exit(1);
        }
    int fd = open((dir + "/frames.bin").c_str(), O_RDONLY);
    struct stat st;
    fstat(fd, &st);
    D.map_len = st.st_size;
    D.base = (const uint8_t *)mmap(nullptr, D.map_len, PROT_READ, MAP_PRIVATE, fd, 0);
    close(fd);
    if (D.base == MAP_FAILED) {
        fprintf(stderr, "mmap failed\n");
        exit(1);
    }
}

cv::Mat make_image(const PwviData &D, size_t off, int ds) {
    const uint8_t *src = D.base + off;
    if (ds == 1) {
        cv::Mat m(D.H, D.W, CV_8UC1);
        memcpy(m.data, src, (size_t)D.W * D.H);
        return m;
    }
    int h = D.H / ds, w = D.W / ds;
    cv::Mat m(h, w, CV_8UC1);
    const int n = ds * ds;
    for (int y = 0; y < h; ++y) {
        for (int x = 0; x < w; ++x) {
            int s = 0;
            for (int dy = 0; dy < ds; ++dy)
                for (int dx = 0; dx < ds; ++dx)
                    s += src[(size_t)(y * ds + dy) * D.W + (x * ds + dx)];
            // numpy mean().round(): sum/n correctly rounded then round-half-even.
            double v = std::nearbyint((double)s / (double)n);
            m.at<uint8_t>(y, x) = (uint8_t)v;
        }
    }
    return m;
}

} // namespace

int main(int argc, char **argv) {
    if (argc < 5) {
        fprintf(stderr,
                "usage: %s <slam.yaml> <device.yaml> (euroc://dir|pwvi://run) <out.tum> "
                "[--downscale d] [--intrinsics-jsonl]\n",
                argv[0]);
        return 1;
    }
    const std::string slam_cfg_path = argv[1], dev_cfg_path = argv[2], data_path = argv[3],
                      out_tum = argv[4];
    int ds = 1;
    bool use_k = false, expo_half = false;
    double rate_hz = 0.0, pace = 0.0, rate_frac = 1.0;
    std::string cam_out, hex_out, keyed_out, backend_out;
    for (int i = 5; i < argc; ++i) {
        if (!strcmp(argv[i], "--rate-hz") && i + 1 < argc) { rate_hz = atof(argv[++i]); continue; }
        if (!strcmp(argv[i], "--pace") && i + 1 < argc) { pace = atof(argv[++i]); continue; }
        if (!strcmp(argv[i], "--rate-frac") && i + 1 < argc) { rate_frac = atof(argv[++i]); continue; }
        if (!strcmp(argv[i], "--camera-out") && i + 1 < argc) { cam_out = argv[++i]; continue; }
        if (!strcmp(argv[i], "--hex-out") && i + 1 < argc) { hex_out = argv[++i]; continue; }
        if (!strcmp(argv[i], "--keyed-out") && i + 1 < argc) { keyed_out = argv[++i]; continue; }
        if (!strcmp(argv[i], "--backend-out") && i + 1 < argc) { backend_out = argv[++i]; continue; }
        if (!strcmp(argv[i], "--drop-before-imu")) { g_drop_before_imu = true; continue; }
        if (!strcmp(argv[i], "--acc-shift-ms") && i + 1 < argc) { g_acc_shift = atof(argv[++i]) * 1e-3; continue; }
        if (!strcmp(argv[i], "--cam-delay-ms") && i + 1 < argc) { g_cam_delay = atof(argv[++i]) * 1e-3; continue; }
        if (!strcmp(argv[i], "--td-extra-ms") && i + 1 < argc) { g_td_extra = atof(argv[++i]) * 1e-3; continue; }
        if (!strcmp(argv[i], "--frame-map-out") && i + 1 < argc) { g_map_out = argv[++i]; continue; }
        if (!strcmp(argv[i], "--limit-frames") && i + 1 < argc) { g_limit_frames = atol(argv[++i]); continue; }
        if (!strcmp(argv[i], "--k-hold") && i + 2 < argc) { g_kmods.push_back({0, atof(argv[i + 1]), atof(argv[i + 2]), 0, 0}); i += 2; continue; }
        if (!strcmp(argv[i], "--k-const") && i + 3 < argc) { g_kmods.push_back({1, atof(argv[i + 1]), atof(argv[i + 2]), atof(argv[i + 3]), 0}); i += 3; continue; }
        if (!strcmp(argv[i], "--k-scale") && i + 3 < argc) { g_kmods.push_back({2, atof(argv[i + 1]), atof(argv[i + 2]), atof(argv[i + 3]), 0}); i += 3; continue; }
        if (!strcmp(argv[i], "--exposure-half"))
            expo_half = true;
        if (!strcmp(argv[i], "--downscale") && i + 1 < argc)
            ds = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--intrinsics-jsonl"))
            use_k = true;
    }
    void *yaml_config = nullptr;
    if (XRSLAMCreate(slam_cfg_path.c_str(), dev_cfg_path.c_str(), "", "pw-s3-runner",
                     &yaml_config) != 1) {
        fprintf(stderr, "XRSLAMCreate failed\n");
        return 1;
    }
    const double time_offset =
        static_cast<xrslam::extra::YamlConfig *>(yaml_config)->camera_time_offset();

    std::vector<PoseRow> traj, ctraj;
    // [bkpose] fed t -> (recording frame, t_ns), exact double key
    std::map<double, std::pair<long long, long long>> rec_of_t;
    std::map<double, std::chrono::steady_clock::time_point> push_wall; // [bkpose] 帧推入时刻(只读计时)
    double cur_fed_t = 0.0;
    FILE *hexf = nullptr, *keyedf = nullptr, *bkf = nullptr;
    double last_keyed_t = -1e300;
    long n_keyed = 0, n_bk = 0;
    unsigned long long bk_dropped_total = 0;
    auto bits = [](double v) { uint64_t u; memcpy(&u, &v, 8); return u; };
#ifdef PW_BKPOSE_TAP
#ifdef PW_BKPOSE_STATE
    // [preint 2026-09-25] 引擎 feat/okvis2-preint 起有 XRSLAMDrainBackendStates:同一条记录 + v / bg / ba,
    // CSV 在原 23 列之后追加 9 列(原列逐字不变)。
    std::vector<XRSLAMBackendState> bkbuf(4096);
    auto bk_write = [&](const XRSLAMBackendState &st) {
        const XRSLAMBackendPose &b = st.pose;
#else
    std::vector<XRSLAMBackendPose> bkbuf(4096);
    auto bk_write = [&](const XRSLAMBackendPose &b) {
#endif
        long long fr = -1, tns = -1;
        auto it = rec_of_t.find(b.timestamp);
        if (it != rec_of_t.end()) { fr = it->second.first; tns = it->second.second; }
        double lat_ms = -1.0;
        auto pw = push_wall.find(b.timestamp);
        if (pw != push_wall.end())
            lat_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - pw->second).count();
        fprintf(bkf, "%.3f,%.9f,", lat_ms, cur_fed_t);
        fprintf(bkf, "%d,%" PRIu64 ",%d,%lld,%lld,%.17g,%016" PRIx64 ",%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,"
                "%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g",
                b.kind, (uint64_t)b.frame_id, b.is_keyframe, fr, tns, b.timestamp, bits(b.timestamp),
                b.translation[0], b.translation[1], b.translation[2], b.quaternion[0], b.quaternion[1],
                b.quaternion[2], b.quaternion[3], b.body_translation[0], b.body_translation[1],
                b.body_translation[2], b.body_quaternion[0], b.body_quaternion[1], b.body_quaternion[2],
                b.body_quaternion[3]);
#ifdef PW_BKPOSE_STATE
        fprintf(bkf, ",%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g", st.velocity[0], st.velocity[1],
                st.velocity[2], st.gyro_bias[0], st.gyro_bias[1], st.gyro_bias[2], st.acc_bias[0], st.acc_bias[1],
                st.acc_bias[2]);
#endif
        fprintf(bkf, "\n");
        ++n_bk;
    };
    auto bk_drain = [&]() {
        if (!bkf) return;
        for (;;) {
            unsigned long long d = 0;
#ifdef PW_BKPOSE_STATE
            int n = XRSLAMDrainBackendStates(bkbuf.data(), (int)bkbuf.size(), &d);
#else
            int n = XRSLAMDrainBackendPoses(bkbuf.data(), (int)bkbuf.size(), &d);
#endif
            bk_dropped_total += d;
            for (int i = 0; i < n; ++i) bk_write(bkbuf[i]);
            if (n < (int)bkbuf.size()) break;
        }
    };
#else
    auto bk_drain = [&]() {};
#endif
    double pace_t0 = -1.0;
    auto pace_wall0 = std::chrono::steady_clock::now();
    auto pace_wait = [&](double t) {
        if (pace <= 0) return;
        if (pace_t0 < 0) { pace_t0 = t; pace_wall0 = std::chrono::steady_clock::now(); return; }
        std::this_thread::sleep_until(pace_wall0 + std::chrono::duration<double>((t - pace_t0) / pace));
    };
    long n_img = 0, n_pose = 0, n_k = 0;
    double last_pose_t = -1.0;
    const auto t_start = std::chrono::steady_clock::now();

    auto push_image = [&](double t, cv::Mat &mat, const std::array<double, 4> *k) {
        XRSLAMImage img{};
        img.data = mat.data;
        img.timeStamp = t;
        img.stride = static_cast<int>(mat.step[0]);
        img.camera_id = 0;
        img.channel = mat.channels();
        XRSLAMImageExtension ext{};
        if (k && std::isfinite((*k)[0])) {
            for (int i = 0; i < 4; ++i)
                ext.intrinsics_fxfycxcy[i] = (*k)[i];
            ext.has_intrinsics = 1;
            img.ext = &ext;
            img.ext_size = static_cast<unsigned int>(sizeof(ext));
            ++n_k;
        }
        push_wall[t] = std::chrono::steady_clock::now();
        cur_fed_t = t;
        XRSLAMPushSensorData(XRSLAM_SENSOR_CAMERA, &img);
        ++n_img;
        XRSLAMRunOneFrame();
        XRSLAMPose pose{};
        XRSLAMGetResult(XRSLAM_RESULT_BODY_POSE, &pose);
        {   // [bkpose] full-precision trace of every existing output, read-only, before any gate
            XRSLAMPose hc{};
            XRSLAMGetResult(XRSLAM_RESULT_CAMERA_POSE, &hc);
            XRSLAMState hs = XRSLAM_STATE_INITIALIZING;
            XRSLAMGetResult(XRSLAM_RESULT_STATE, &hs);
            if (hexf) {
                fprintf(hexf, "%016" PRIx64, bits(t));
                for (int i = 0; i < 4; ++i) fprintf(hexf, " %016" PRIx64, bits(hc.quaternion[i]));
                for (int i = 0; i < 3; ++i) fprintf(hexf, " %016" PRIx64, bits(hc.translation[i]));
                fprintf(hexf, " %016" PRIx64, bits(hc.timestamp));
                for (int i = 0; i < 4; ++i) fprintf(hexf, " %016" PRIx64, bits(pose.quaternion[i]));
                for (int i = 0; i < 3; ++i) fprintf(hexf, " %016" PRIx64, bits(pose.translation[i]));
                fprintf(hexf, " %016" PRIx64 " %d\n", bits(pose.timestamp), (int)hs);
            }
            const double cqn = std::sqrt(hc.quaternion[0] * hc.quaternion[0] + hc.quaternion[1] * hc.quaternion[1] +
                                         hc.quaternion[2] * hc.quaternion[2] + hc.quaternion[3] * hc.quaternion[3]);
            auto rit = rec_of_t.find(t);
            if (keyedf && hs == XRSLAM_STATE_TRACKING_SUCCESS && cqn >= 0.5 && hc.timestamp > last_keyed_t &&
                rit != rec_of_t.end()) {
                last_keyed_t = hc.timestamp;
                fprintf(keyedf, "%lld,%lld,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f,%.9f\n", rit->second.first,
                        rit->second.second, hc.translation[0], hc.translation[1], hc.translation[2],
                        hc.quaternion[0], hc.quaternion[1], hc.quaternion[2], hc.quaternion[3], hc.timestamp);
                ++n_keyed;
            }
            bk_drain();
        }
        const double qn = std::sqrt(pose.quaternion[0] * pose.quaternion[0] +
                                    pose.quaternion[1] * pose.quaternion[1] +
                                    pose.quaternion[2] * pose.quaternion[2] +
                                    pose.quaternion[3] * pose.quaternion[3]);
        if (qn < 0.5 || !(pose.timestamp > last_pose_t))
            return;
        last_pose_t = pose.timestamp;
        PoseRow r;
        r.t = pose.timestamp;
        for (int i = 0; i < 4; ++i)
            r.q[i] = pose.quaternion[i];
        for (int i = 0; i < 3; ++i)
            r.p[i] = pose.translation[i];
        traj.push_back(r);
        ++n_pose;
        XRSLAMPose cp{};
        XRSLAMGetResult(XRSLAM_RESULT_CAMERA_POSE, &cp);
        PoseRow c;
        c.t = cp.timestamp;
        for (int i = 0; i < 4; ++i)
            c.q[i] = cp.quaternion[i];
        for (int i = 0; i < 3; ++i)
            c.p[i] = cp.translation[i];
        ctraj.push_back(c);
    };

    if (data_path.rfind("pwvi://", 0) == 0) {
        PwviData D;
        load_pwvi(data_path.substr(7), time_offset, ds, use_k, expo_half, rate_hz, rate_frac, D);
        for (size_t i = 0; i < D.cams.size(); ++i)
            rec_of_t[D.cams[i].first] = {D.cam_fid[i], D.cam_tns[i]};
        if (!hex_out.empty()) hexf = fopen(hex_out.c_str(), "w");
        if (!keyed_out.empty()) {
            keyedf = fopen(keyed_out.c_str(), "w");
            fprintf(keyedf, "recording_frame,t_ns,tx,ty,tz,qx,qy,qz,qw,engine_t\n");
        }
#ifdef PW_BKPOSE_TAP
        if (!backend_out.empty()) {
            bkf = fopen(backend_out.c_str(), "w");
            fprintf(bkf, "ms_since_push,fed_t_at_drain,kind,frame_id,is_keyframe,recording_frame,t_ns,engine_t,engine_t_hex,tx,ty,tz,qx,qy,qz,qw,"
                         "body_tx,body_ty,body_tz,body_qx,body_qy,body_qz,body_qw"
#ifdef PW_BKPOSE_STATE
                         ",vx,vy,vz,bgx,bgy,bgz,bax,bay,baz"
#endif
                         "\n");
        }
#else
        if (!backend_out.empty()) { fprintf(stderr, "--backend-out needs -DPW_BKPOSE_TAP\n"); return 1; }
#endif
        if (!g_map_out.empty()) {
            FILE *mf = fopen(g_map_out.c_str(), "w");
            for (size_t i = 0; i < D.cams.size(); ++i)
                fprintf(mf, "%.9f %lld\n", D.cams[i].first, D.cam_tns[i]);
            fclose(mf);
        }
        for (const Ev &e : D.events) {
            pace_wait(e.t);
            if (e.type == 1) {
                XRSLAMGyroscope g = {{D.imu[e.idx][1], D.imu[e.idx][2], D.imu[e.idx][3]},
                                     D.imu[e.idx][0]};
                XRSLAMPushSensorData(XRSLAM_SENSOR_GYROSCOPE, &g);
            } else if (e.type == 2) {
                XRSLAMAcceleration a = {{D.imu[e.idx][4], D.imu[e.idx][5], D.imu[e.idx][6]},
                                        D.imu[e.idx][0] + g_acc_shift};
                XRSLAMPushSensorData(XRSLAM_SENSOR_ACCELERATION, &a);
            } else {
                cv::Mat m = make_image(D, D.cams[e.idx].second, ds);
                push_image(D.cams[e.idx].first, m, use_k ? &D.cam_k[e.idx] : nullptr);
            }
        }
    } else {
        // leaked on purpose: EurocDatasetReader wraps the engine-owned YamlConfig in a shared_ptr
        // (euroc_dataset_reader.cpp:5-6) -> destroying it double-frees (the known teardown crash).
        DatasetReader *reader = DatasetReader::create_reader(data_path, yaml_config, false).release();
        if (!reader) {
            fprintf(stderr, "cannot open dataset %s\n", data_path.c_str());
            return 1;
        }
        DatasetReader::NextDataType type;
        while ((type = reader->next()) != DatasetReader::END) {
            switch (type) {
            case DatasetReader::AGAIN:
                continue;
            case DatasetReader::GYROSCOPE: {
                auto [t, g] = reader->read_gyroscope();
                (void)t;
                XRSLAMPushSensorData(XRSLAM_SENSOR_GYROSCOPE, &g);
            } break;
            case DatasetReader::ACCELEROMETER: {
                auto [t, a] = reader->read_accelerometer();
                (void)t;
                XRSLAMPushSensorData(XRSLAM_SENSOR_ACCELERATION, &a);
            } break;
            case DatasetReader::CAMERA: {
                auto [t, mat] = reader->read_image();
                if (mat.empty())
                    break;
                push_image(t, mat, nullptr);
            } break;
            default:
                break;
            }
        }
    }
    const double wall_s =
        std::chrono::duration<double>(std::chrono::steady_clock::now() - t_start).count();
#ifdef PW_BKPOSE_TAP
    if (bkf) {
        // all inputs are in; let the workers finish what is queued (no new input => no effect on
        // anything already written above), then take the tail and the last window snapshot.
        for (int i = 0; i < 400 && XRSLAMGetPendingWorkerFrames() > 0; ++i)
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        bk_drain();
#ifdef PW_BKPOSE_STATE
        int nw = XRSLAMGetBackendWindowStates(bkbuf.data(), (int)bkbuf.size());
#else
        int nw = XRSLAMGetBackendWindowPoses(bkbuf.data(), (int)bkbuf.size());
#endif
        for (int i = 0; i < nw && i < (int)bkbuf.size(); ++i) bk_write(bkbuf[i]);
        fclose(bkf);
        fprintf(stderr, "=== bkpose: backend rows %ld (window %d) dropped %llu\n", n_bk, nw, bk_dropped_total);
    }
#endif
    if (hexf) fclose(hexf);
    if (keyedf) { fclose(keyedf); fprintf(stderr, "=== bkpose: keyed front-end rows %ld\n", n_keyed); }
    std::ofstream out(out_tum);
    out.setf(std::ios::fixed);
    for (const PoseRow &r : traj) {
        out.precision(9);
        out << r.t << ' ';
        out.precision(7);
        out << r.p[0] << ' ' << r.p[1] << ' ' << r.p[2] << ' ' << r.q[0] << ' ' << r.q[1] << ' '
            << r.q[2] << ' ' << r.q[3] << '\n';
    }
    out.close();
    if (!cam_out.empty()) {
        std::ofstream co(cam_out);
        co.setf(std::ios::fixed);
        for (const PoseRow &r : ctraj) {
            co.precision(9);
            co << r.t << ' ';
            co.precision(7);
            co << r.p[0] << ' ' << r.p[1] << ' ' << r.p[2] << ' ' << r.q[0] << ' ' << r.q[1] << ' '
               << r.q[2] << ' ' << r.q[3] << '\n';
        }
    }
    fprintf(stderr, "=== s3 runner: images %ld poses %ld K %ld wall %.1f s -> %s\n", n_img, n_pose,
            n_k, wall_s, out_tum.c_str());
    fflush(nullptr); // flush every stdio stream incl. the engine-side PW_S3_LOG FILE*
    _exit(traj.empty() ? 1 : 0); // skip static destructors (known exit-11 at teardown in pw tools)
}
