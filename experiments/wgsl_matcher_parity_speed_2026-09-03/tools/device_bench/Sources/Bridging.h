#pragma once
#ifdef __cplusplus
extern "C" {
#endif
// 返回写出的结果文件路径(在 app 的 Documents 下);失败返回空串。
const char* pwbench_run(const char* fixture_dir, int rows, int reps,
                        double ratio, const char* out_dir);
#ifdef __cplusplus
}
#endif
