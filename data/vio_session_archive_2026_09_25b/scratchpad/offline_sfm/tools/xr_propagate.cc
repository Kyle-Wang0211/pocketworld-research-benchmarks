// xr_propagate.cc — [offline_sfm 2026-09-25 外推轮] 用 XRSLAM 引擎**自己的** propagate_state
// 把一个给定的后端状态(时刻、body 位姿 q/p、速度 v、零偏 bg/ba)沿 IMU 外推到目标时刻。
//
// 不重写外推:本文件把引擎源码 detail.cpp(bkpose/xrslam-wt @8ebac9a,只读)原样 #include 进来,
// 因为 propagate_state 在那里是文件内 static 函数,只有同一编译单元能调用。Detail 类的其余成员
// 由 bkpose 现成的 libxrslam.dylib(同一份源码构建)解析,本工具只调用 propagate_state。
// 编译旗标照抄 bkpose/build-mac/build.ninja 里 xrslam-core 的 detail.cpp 那条(-O3 -ffp-contract=off
// -fno-fast-math ...),保证浮点行为一致。
//
// 与 Detail::predict_pose(detail.cpp:147-173)逐句对应:
//   * 先丢掉 t <= state_time 的 IMU 样本,再对 imu.t <= t 的每个样本调用 propagate_state;
//     不补「最后一个样本 → t」那一小段(引擎就是这样);
//   * 输出 body 位姿 = state_pose × output_to_body(detail.cpp:167-169);
//   * 相机位姿 = 输出位姿 × camera_to_body(XRSLAMManager.cpp:342-343 GetResultCameraPose);
//   * 外参来自引擎自己的 extra::YamlConfig(同一份 slam_config.yaml / dev_<scene>.yaml)。
// IMU 样本 = 录制 imu.csv 原值,时间戳 strtod(ns 串)×1e-9(pwvi_runner.cpp:335-352 同法);
// 回放器在同一时刻先推陀螺再推加速度,引擎 track_accelerometer 在 t == gyroscopes.back().t 分支
// 直接合成 {t, w, a}(detail.cpp:81-86),所以 frontal_imus 就是逐行 (t, w, a)。
//
// 用法:xr_propagate <slam.yaml> <dev.yaml> <imu.csv> <jobs.txt> <out.txt>
//   jobs 每行:id t_state px py pz qx qy qz qw vx vy vz bgx bgy bgz bax bay baz t_target
//   out 每行:id t_state t_target t_last_imu n_imu  bpx bpy bpz bqx bqy bqz bqw  cpx cpy cpz cqx cqy cqz cqw
#include "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/bkpose/xrslam-wt/xrslam/src/xrslam/core/detail.cpp"

#include <xrslam/extra/yaml_config.h>

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

namespace {
struct Imu {
    double t;
    xrslam::vector<3> w, a;
};
}  // namespace

int main(int argc, char **argv) {
    if (argc < 6) {
        std::fprintf(stderr, "usage: %s <slam.yaml> <dev.yaml> <imu.csv> <jobs.txt> <out.txt>\n", argv[0]);
        return 1;
    }
    xrslam::extra::YamlConfig cfg(argv[1], argv[2]);
    const xrslam::quaternion q_ob = cfg.output_to_body_rotation();
    const xrslam::vector<3> p_ob = cfg.output_to_body_translation();
    const xrslam::quaternion q_cb = cfg.camera_to_body_rotation();
    const xrslam::vector<3> p_cb = cfg.camera_to_body_translation();

    std::vector<Imu> imus;
    {
        std::ifstream f(argv[3]);
        std::string ln;
        std::getline(f, ln);
        while (std::getline(f, ln)) {
            if (ln.empty()) continue;
            double r[7];
            const char *c = ln.c_str();
            char *e;
            for (int i = 0; i < 7; ++i) {
                r[i] = std::strtod(c, &e);
                c = e + 1;
            }
            r[0] *= 1e-9;
            imus.push_back({r[0], {r[1], r[2], r[3]}, {r[4], r[5], r[6]}});
        }
    }
    std::FILE *out = std::fopen(argv[5], "w");
    std::ifstream jf(argv[4]);
    std::string ln;
    long n_jobs = 0;
    while (std::getline(jf, ln)) {
        if (ln.empty() || ln[0] == '#') continue;
        char id[128];
        double v[19];
        const char *c = ln.c_str();
        if (std::sscanf(c, "%127s", id) != 1) continue;
        c += std::strlen(id);
        char *e;
        for (int i = 0; i < 19; ++i) {
            v[i] = std::strtod(c, &e);
            c = e;
        }
        double state_time = v[0];
        xrslam::PoseState state_pose;
        xrslam::MotionState state_motion;
        state_pose.p = {v[1], v[2], v[3]};
        state_pose.q = xrslam::quaternion(v[7], v[4], v[5], v[6]);  // Eigen(w, x, y, z)
        state_motion.v = {v[8], v[9], v[10]};
        state_motion.bg = {v[11], v[12], v[13]};
        state_motion.ba = {v[14], v[15], v[16]};
        const double t = v[17];
        const double t_state0 = state_time;
        int n_imu = 0;
        for (const Imu &imu : imus) {           // predict_pose:丢弃 t <= state_time,再推 imu.t <= t
            if (imu.t <= t_state0) continue;
            if (imu.t > t) break;
            xrslam::propagate_state(state_time, state_pose, state_motion, imu.t, imu.w, imu.a);
            ++n_imu;
        }
        xrslam::Pose output_pose;               // detail.cpp:167-169
        output_pose.q = state_pose.q * q_ob;
        output_pose.p = state_pose.p + state_pose.q * p_ob;
        xrslam::Pose camera_pose;               // XRSLAMManager.cpp:342-343
        camera_pose.q = output_pose.q * q_cb;
        camera_pose.p = output_pose.p + output_pose.q * p_cb;
        std::fprintf(out, "%s %.9f %.9f %.9f %d", id, t_state0, t, state_time, n_imu);
        std::fprintf(out, " %.17g %.17g %.17g %.17g %.17g %.17g %.17g", output_pose.p.x(), output_pose.p.y(),
                     output_pose.p.z(), output_pose.q.x(), output_pose.q.y(), output_pose.q.z(), output_pose.q.w());
        std::fprintf(out, " %.17g %.17g %.17g %.17g %.17g %.17g %.17g\n", camera_pose.p.x(), camera_pose.p.y(),
                     camera_pose.p.z(), camera_pose.q.x(), camera_pose.q.y(), camera_pose.q.z(), camera_pose.q.w());
        ++n_jobs;
    }
    std::fclose(out);
    std::fprintf(stderr, "xr_propagate: imu %zu 条,作业 %ld 个;外参 q_cb=[%.9g %.9g %.9g %.9g] p_cb=[%.9g %.9g %.9g]\n",
                 imus.size(), n_jobs, q_cb.x(), q_cb.y(), q_cb.z(), q_cb.w(), p_cb.x(), p_cb.y(), p_cb.z());
    return 0;
}
