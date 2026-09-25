// pwvi_runner.cpp -- S3 scratch tool (not for commit).
// [xrhires 2026-09-24] + --resize WxH (cv::INTER_AREA from the full-res Y plane, for non-integer
//   factors such as 1280x960; per-frame K scaled with the same pixel-centre convention as --downscale),
//   + --zone-stats <path> (dump PW_ZONE wall-clock stats, needs a -DPW_ZONE_STATS engine build),
//   + --feed-ms-out <path> (caller-side ms of Push(camera)+RunOneFrame per frame).
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

extern "C" void pw_zone_stats_dump(const char *path) __attribute__((weak_import));

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

static int g_rw = 0, g_rh = 0; // [xrhires] --resize target
void load_pwvi(const std::string &dir, double time_offset, int ds, bool use_k, bool expo_half,
               double rate_hz, double rate_frac, PwviData &D) {
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
        while (std::getline(f, ln)) {
            if (ln.empty())
                continue;
            size_t comma = ln.find(',');
            std::string ts = ln.substr(0, comma);
            long long fid = atoll(ln.c_str() + comma + 1);
            auto it = off_by_frame.find(fid);
            if (it == off_by_frame.end()) {
                ++n_missing;
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
            D.cams.push_back({t, (size_t)it->second});
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
                    kk = {(*best)[0] / d, (*best)[1] / d, ((*best)[2] + 0.5) / d - 0.5,
                          ((*best)[3] + 0.5) / d - 0.5};
                    if (g_rw > 0) { // [xrhires] resize: s = W'/W (x), H'/H (y)
                        const double sx = (double)g_rw / D.W, sy = (double)g_rh / D.H;
                        kk = {(*best)[0] * sx, (*best)[1] * sy, ((*best)[2] + 0.5) * sx - 0.5,
                              ((*best)[3] + 0.5) * sy - 0.5};
                    }
                } else {
                    ++n_kmiss;
                }
            }
            D.cam_k.push_back(kk);
        }
        fprintf(stderr, "[pwvi] cams %zu (missing %zu, rate-dropped %zu @%.1f Hz) Kmiss %zu  W×H %d×%d ds %d\n",
                D.cams.size(), n_missing, n_rate_drop, rate_hz, n_kmiss, D.W, D.H, ds);
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
        D.events.push_back({D.cams[i].first, 0, i});
    for (size_t i = 0; i < D.imu.size(); ++i) {
        D.events.push_back({D.imu[i][0], 1, i});
        D.events.push_back({D.imu[i][0], 2, i});
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
    if (g_rw > 0) { // [xrhires]
        cv::Mat full(D.H, D.W, CV_8UC1, const_cast<uint8_t *>(src));
        cv::Mat m;
        cv::resize(full, m, cv::Size(g_rw, g_rh), 0, 0, cv::INTER_AREA);
        return m;
    }
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
    std::string cam_out, zone_out, feed_out;
    for (int i = 5; i < argc; ++i) {
        if (!strcmp(argv[i], "--rate-hz") && i + 1 < argc) { rate_hz = atof(argv[++i]); continue; }
        if (!strcmp(argv[i], "--pace") && i + 1 < argc) { pace = atof(argv[++i]); continue; }
        if (!strcmp(argv[i], "--rate-frac") && i + 1 < argc) { rate_frac = atof(argv[++i]); continue; }
        if (!strcmp(argv[i], "--camera-out") && i + 1 < argc) { cam_out = argv[++i]; continue; }
        if (!strcmp(argv[i], "--zone-stats") && i + 1 < argc) { zone_out = argv[++i]; continue; }
        if (!strcmp(argv[i], "--feed-ms-out") && i + 1 < argc) { feed_out = argv[++i]; continue; }
        if (!strcmp(argv[i], "--resize") && i + 1 < argc) {
            if (sscanf(argv[++i], "%dx%d", &g_rw, &g_rh) != 2) { fprintf(stderr, "bad --resize\n"); return 1; }
            continue;
        }
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

    std::vector<float> feed_ms;
    auto push_image = [&](double t, cv::Mat &mat, const std::array<double, 4> *k) {
        const auto f0 = std::chrono::steady_clock::now();
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
        XRSLAMPushSensorData(XRSLAM_SENSOR_CAMERA, &img);
        ++n_img;
        XRSLAMRunOneFrame();
        feed_ms.push_back(std::chrono::duration<float, std::milli>(std::chrono::steady_clock::now() - f0).count());
        XRSLAMPose pose{};
        XRSLAMGetResult(XRSLAM_RESULT_BODY_POSE, &pose);
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
        for (const Ev &e : D.events) {
            pace_wait(e.t);
            if (e.type == 1) {
                XRSLAMGyroscope g = {{D.imu[e.idx][1], D.imu[e.idx][2], D.imu[e.idx][3]},
                                     D.imu[e.idx][0]};
                XRSLAMPushSensorData(XRSLAM_SENSOR_GYROSCOPE, &g);
            } else if (e.type == 2) {
                XRSLAMAcceleration a = {{D.imu[e.idx][4], D.imu[e.idx][5], D.imu[e.idx][6]},
                                        D.imu[e.idx][0]};
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
    if (!zone_out.empty()) {
        if (pw_zone_stats_dump) pw_zone_stats_dump(zone_out.c_str());
        else fprintf(stderr, "--zone-stats: engine built without PW_ZONE_STATS\n");
    }
    if (!feed_out.empty()) {
        std::ofstream fo(feed_out);
        for (float x : feed_ms) fo << x << '\n';
    }
    fprintf(stderr, "[xrhires] resize %dx%d\n", g_rw, g_rh);
    fprintf(stderr, "=== s3 runner: images %ld poses %ld K %ld wall %.1f s -> %s\n", n_img, n_pose,
            n_k, wall_s, out_tum.c_str());
    fflush(nullptr); // flush every stdio stream incl. the engine-side PW_S3_LOG FILE*
    _exit(traj.empty() ? 1 : 0); // skip static destructors (known exit-11 at teardown in pw tools)
}
