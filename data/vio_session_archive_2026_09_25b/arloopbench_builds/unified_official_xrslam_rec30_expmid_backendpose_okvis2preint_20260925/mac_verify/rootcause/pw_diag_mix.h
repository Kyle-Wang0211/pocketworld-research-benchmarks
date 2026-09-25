#ifndef XRSLAM_PW_DIAG_MIX_H
#define XRSLAM_PW_DIAG_MIX_H
// [诊断补丁,不入库 2026-09-25] 混合臂:每帧同时维护旧写法样本(data)与新写法样本(data_raw),
// 各调用点按环境变量 PW_MIX_NEW 选旧积分器(8ebac9a 原样)或新积分器(4e8dda2 原样)。
//   PW_MIX_NEW 未设 = 全新;"none" = 全旧;否则逗号列表 backend,front,prop,init 里列出的用新。
// PW_DIAG_LOG=<路径>:逐帧写跟踪 / 关键帧 / 初始化日志(只读打点,不改计算)。
#include <xrslam/common.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
namespace xrslam {
enum PwMixSite { kMixBackend = 1, kMixFront = 2, kMixProp = 4, kMixInit = 8 };
inline int pw_mix_mask() {
    static const int m = [] {
        const char *s = getenv("PW_MIX_NEW");
        if (!s || strstr(s, "all")) return 15;
        int r = 0;
        if (strstr(s, "backend")) r |= kMixBackend;
        if (strstr(s, "front")) r |= kMixFront;
        if (strstr(s, "prop")) r |= kMixProp;
        if (strstr(s, "init")) r |= kMixInit;
        return r;
    }();
    return m;
}
inline bool pw_mix_new(int site) { return (pw_mix_mask() & site) != 0; }
inline FILE *pw_diag_log() {
    static FILE *f = [] {
        const char *p = getenv("PW_DIAG_LOG");
        return p ? fopen(p, "w") : (FILE *)nullptr;
    }();
    return f;
}
} // namespace xrslam
#endif
