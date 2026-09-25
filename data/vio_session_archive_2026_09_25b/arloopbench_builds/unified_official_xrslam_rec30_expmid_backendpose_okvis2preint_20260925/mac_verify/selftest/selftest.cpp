// [preint 2026-09-25] 自检(scratch,不入库):OKVIS2 离散的预积分器 vs 解析真值 / 有限差分 / 蒙特卡洛。
#include <xrslam/estimation/preintegrator.h>
#include <xrslam/geometry/lie_algebra.h>
#include <cstdio>
#include <random>
using namespace xrslam;

// 连续运动:ω(t) = [0.8 sin(2π·1.3 t), 1.1 cos(2π·0.7 t), 0.5 sin(2π·2.1 t + 0.3)] rad/s(机体系),
// a(t) = [0.6 sin(2π·0.9 t), 0.4 cos(2π·1.7 t), 9.8 + 0.3 sin(2π·0.5 t)](机体系比力)
static vector<3> W(double t) { return {0.8 * sin(2 * M_PI * 1.3 * t), 1.1 * cos(2 * M_PI * 0.7 * t), 0.5 * sin(2 * M_PI * 2.1 * t + 0.3)}; }
static vector<3> A(double t) { return {0.6 * sin(2 * M_PI * 0.9 * t), 0.4 * cos(2 * M_PI * 1.7 * t), 9.8 + 0.3 * sin(2 * M_PI * 0.5 * t)}; }

// 真值:1 µs 步长 RK4 式细积分(四元数 + 双重积分)
static void truth(double t0, double t1, quaternion &q, vector<3> &v, vector<3> &p) {
    const int N = (int)std::round((t1 - t0) / 1e-5);
    const double h = (t1 - t0) / N;
    q.setIdentity(); v.setZero(); p.setZero();
    for (int k = 0; k < N; ++k) {
        double t = t0 + k * h;
        vector<3> wm = W(t + 0.5 * h);
        quaternion qm = q * expmap(W(t) * 0.5 * h);
        vector<3> a0 = q * A(t), am = qm * A(t + 0.5 * h);
        quaternion q1 = q * expmap(wm * h);
        vector<3> a1 = q1 * A(t + h);
        p += v * h + h * h / 6.0 * (a0 + 2 * am);
        v += h / 6.0 * (a0 + 4 * am + a1);
        q = q1.normalized();
    }
}

int main() {
    const double fs = 100.0, t_first = 0.0012;
    std::vector<ImuData> all;
    for (int k = 0; k < 400; ++k) { double t = t_first + k / fs; all.push_back({t, W(t), A(t)}); }
    auto slice = [&](double t0, double t1) {
        std::vector<ImuData> d;
        for (size_t k = 0; k < all.size(); ++k) {
            bool pre = (k + 1 < all.size() && all[k].t <= t0 && all[k + 1].t > t0);
            bool in = all[k].t > t0 && all[k].t <= t1;
            bool post = (k > 0 && all[k - 1].t <= t1 && all[k].t > t1);
            if (pre || in || post) d.push_back(all[k]);
        }
        return d;
    };
    PreIntegrator pi;
    pi.cov_w = matrix<3>::Identity() * 2.8791302399999997e-8; pi.cov_a = matrix<3>::Identity() * 4e-6;
    pi.cov_bg = matrix<3>::Identity() * 3.7608844899999997e-10; pi.cov_ba = matrix<3>::Identity() * 9e-6;
    // 1) 与解析真值比:姿态误差、以及等效时间偏移(误差在 ω 方向上的投影 / |ω|)
    printf("== 1) 均值 vs 细积分真值(33 ms 帧间隔,起止不在采样点上)\n");
    double worst = 0;
    for (int i = 0; i < 5; ++i) {
        double t0 = 0.5 + 0.0333 * i + 0.0037 * i, t1 = t0 + 0.0333;
        pi.data = slice(t0, t1);
        pi.integrate(t0, t1, vector<3>::Zero(), vector<3>::Zero(), true, true);
        quaternion qt; vector<3> vt, pt; truth(t0, t1, qt, vt, pt);
        vector<3> e = logmap(qt.conjugate() * pi.delta.q);
        worst = std::max(worst, e.norm());
        printf("  [%.4f,%.4f] n=%zu |dθ|=%.3e rad  |dv|=%.3e  |dp|=%.3e  dt=%.6f\n", t0, t1, pi.data.size(), e.norm(), (pi.delta.v - vt).norm(), (pi.delta.p - pt).norm(), pi.delta.t);
    }
    // 对照:上游 8ebac9a 的左端零阶保持(帧起点插「上一帧末样本、时间戳改成 t0」的拷贝,每段用段首样本),
    // 用同一套样本积;误差投影到 ω 上折算成等效时间偏移 δt = e·ω/|ω|²(负 = 积出的姿态落后于时间戳)
    printf("== 1b) 等效时间偏移 s:扫 s 使 Σ|log(ΔR_积分^T · ΔR_真值[a+s, b+s])|² 最小(100 个 33 ms 区间)\n");
    {
        std::mt19937_64 r2(3); std::uniform_real_distribution<double> U(0.3, 3.3);
        std::vector<double> A0; for (int i = 0; i < 100; ++i) A0.push_back(U(r2));
        std::vector<quaternion> qn, qo;
        for (double a : A0) {
            double b = a + 0.0333;
            pi.data = slice(a, b); pi.integrate(a, b, vector<3>::Zero(), vector<3>::Zero(), false, false); qn.push_back(pi.delta.q);
            std::vector<ImuData> d; ImuData last{}; bool have = false;
            for (auto &x : all) { if (x.t <= a) { last = x; have = true; } }
            last.t = a; if (have) d.push_back(last);
            for (auto &x : all) if (x.t > a && x.t <= b) d.push_back(x);
            quaternion q; q.setIdentity();
            for (size_t k = 0; k < d.size(); ++k) { double tn = (k + 1 < d.size()) ? d[k + 1].t : b; q = (q * expmap(d[k].w * (tn - d[k].t))).normalized(); }
            qo.push_back(q);
        }
        auto fit = [&](const std::vector<quaternion> &Q) {
            double best = 1e9, bs = 0, rms = 0;
            for (double sft = -0.008; sft <= 0.008 + 1e-12; sft += 0.0001) {
                double c = 0;
                for (size_t i = 0; i < A0.size(); ++i) { quaternion qt; vector<3> vt, pt; truth(A0[i] + sft, A0[i] + 0.0333 + sft, qt, vt, pt); c += logmap(Q[i].conjugate() * qt).squaredNorm(); }
                if (c < best) { best = c; bs = sft; rms = sqrt(c / A0.size()); }
            }
            printf("    s* = %+.1f ms,残差 RMS %.2e rad\n", 1e3 * bs, rms);
        };
        printf("  OKVIS2 离散:"); fit(qn);
        printf("  上游左端零阶保持:"); fit(qo);
    }
    // 2) 偏置雅可比:有限差分
    printf("== 2) 偏置雅可比 有限差分(δ=1e-4)\n");
    double t0 = 0.61, t1 = 0.7143;   // 跨 ~10 个样本
    pi.data = slice(t0, t1);
    vector<3> bg0{0.01, -0.02, 0.005}, ba0{0.05, 0.02, -0.03};
    pi.integrate(t0, t1, bg0, ba0, true, true);
    PreIntegrator::Delta D0 = pi.delta; PreIntegrator::Jacobian J = pi.jacobian;
    double maxe[5] = {0, 0, 0, 0, 0};
    for (int k = 0; k < 3; ++k) {
        vector<3> d = vector<3>::Zero(); d[k] = 1e-4;
        pi.integrate(t0, t1, bg0 + d, ba0, false, false);
        vector<3> eq = logmap((D0.q * expmap(J.dq_dbg * d)).conjugate() * pi.delta.q);
        vector<3> ep = pi.delta.p - (D0.p + J.dp_dbg * d), ev = pi.delta.v - (D0.v + J.dv_dbg * d);
        maxe[0] = std::max(maxe[0], eq.norm() / 1e-4); maxe[1] = std::max(maxe[1], ep.norm() / 1e-4); maxe[2] = std::max(maxe[2], ev.norm() / 1e-4);
        pi.integrate(t0, t1, bg0, ba0 + d, false, false);
        ep = pi.delta.p - (D0.p + J.dp_dba * d); ev = pi.delta.v - (D0.v + J.dv_dba * d);
        maxe[3] = std::max(maxe[3], ep.norm() / 1e-4); maxe[4] = std::max(maxe[4], ev.norm() / 1e-4);
    }
    printf("  相对残差(应 ~1e-4 量级 = 二阶项):dq/dbg %.2e  dp/dbg %.2e  dv/dbg %.2e  dp/dba %.2e  dv/dba %.2e\n", maxe[0], maxe[1], maxe[2], maxe[3], maxe[4]);
    printf("  雅可比幅值:|dq_dbg| %.3e |dp_dbg| %.3e |dv_dbg| %.3e |dp_dba| %.3e |dv_dba| %.3e\n", J.dq_dbg.norm(), J.dp_dbg.norm(), J.dv_dbg.norm(), J.dp_dba.norm(), J.dv_dba.norm());
    // 3) 协方差:蒙特卡洛(只加白噪声 + 偏置随机游走按样本步进),XRSLAM 残差口径
    printf("== 3) 协方差 蒙特卡洛(20000 次)vs 传播值\n");
    std::mt19937_64 rng(7); std::normal_distribution<double> N01;
    const double sg = sqrt(2.8791302399999997e-8), sa = 2e-3, sbg = sqrt(3.7608844899999997e-10), sba = 3e-3;
    std::vector<ImuData> clean = pi.data;
    const int M = 20000; matrix<15> C = matrix<15>::Zero();
    for (int m = 0; m < M; ++m) {
        pi.data = clean;
        vector<3> bgw = vector<3>::Zero(), baw = vector<3>::Zero();
        for (size_t k = 0; k < pi.data.size(); ++k) {
            double h = 1.0 / fs;
            for (int j = 0; j < 3; ++j) { pi.data[k].w[j] += sg / sqrt(h) * N01(rng) + bgw[j]; pi.data[k].a[j] += sa / sqrt(h) * N01(rng) + baw[j]; }
            for (int j = 0; j < 3; ++j) { bgw[j] += sbg * sqrt(h) * N01(rng); baw[j] += sba * sqrt(h) * N01(rng); }
        }
        pi.integrate(t0, t1, bg0, ba0, false, false);
        Eigen::Matrix<double, 15, 1> r;
        r.segment<3>(0) = logmap(D0.q.conjugate() * pi.delta.q);
        r.segment<3>(3) = pi.delta.p - D0.p; r.segment<3>(6) = pi.delta.v - D0.v;
        r.segment<3>(9) = bgw; r.segment<3>(12) = baw;   // 区间末的偏置变化(近似)
        C += r * r.transpose() / M;
    }
    pi.data = clean; pi.integrate(t0, t1, bg0, ba0, true, true);
    const char *nm[5] = {"q", "p", "v", "bg", "ba"};
    for (int b = 0; b < 3; ++b) {
        printf("  块 %s-%s  传播 diag %.3e %.3e %.3e | MC diag %.3e %.3e %.3e\n", nm[b], nm[b], pi.delta.cov(3*b,3*b), pi.delta.cov(3*b+1,3*b+1), pi.delta.cov(3*b+2,3*b+2), C(3*b,3*b), C(3*b+1,3*b+1), C(3*b+2,3*b+2));
    }
    printf("  块 q-v 传播 Frobenius %.3e  MC %.3e;块 p-v 传播 %.3e MC %.3e\n", pi.delta.cov.block<3,3>(0,6).norm(), C.block<3,3>(0,6).norm(), pi.delta.cov.block<3,3>(3,6).norm(), C.block<3,3>(3,6).norm());
    printf("  q 块在 XRSLAM 右扰动口径下的相关系数矩阵(传播 vs MC)对角外最大差 %.3f\n", [&]{ double mx=0; for(int i=0;i<3;i++)for(int j=0;j<3;j++){ if(i==j)continue; double a=pi.delta.cov(i,j)/sqrt(pi.delta.cov(i,i)*pi.delta.cov(j,j)); double b=C(i,j)/sqrt(C(i,i)*C(j,j)); mx=std::max(mx,fabs(a-b)); } return mx; }());
    return 0;
}
