// official_dense.ply -> cloud.bin(台架吃的 16 B/点格式:xyz f32 + rgba u32)
// 顺带打印这朵云的几何统计,用来定相机档位与 baseScale。
// 只在 Mac 上跑,不进设备。
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <string>
#include <vector>
#include <algorithm>
#include <unordered_set>

struct Pt { float x, y, z; uint32_t rgba; };

int main(int argc, char** argv) {
    const char* in = argc > 1 ? argv[1] : "official_dense.ply";
    const char* out = argc > 2 ? argv[2] : "cloud.bin";
    FILE* f = std::fopen(in, "rb");
    if (!f) { std::fprintf(stderr, "open %s failed\n", in); return 1; }

    // 解析 header(只支持这一种:binary_little_endian, x/y/z float + r/g/b uchar)
    std::string hdr;
    char c;
    while (std::fread(&c, 1, 1, f) == 1) {
        hdr += c;
        if (hdr.size() >= 11 &&
            hdr.compare(hdr.size() - 11, 11, "end_header\n") == 0) break;
    }
    const long hdr_bytes = std::ftell(f);
    size_t n = 0;
    {
        const char* p = std::strstr(hdr.c_str(), "element vertex ");
        if (!p) { std::fprintf(stderr, "no element vertex\n"); return 1; }
        n = (size_t)std::strtoull(p + 15, nullptr, 10);
    }
    const bool ok_fmt = hdr.find("binary_little_endian") != std::string::npos &&
                        hdr.find("property float x") != std::string::npos &&
                        hdr.find("property uchar red") != std::string::npos;
    std::printf("header %ld B, vertices %zu, format-ok %d\n", hdr_bytes, n, (int)ok_fmt);
    if (!ok_fmt) { std::fprintf(stderr, "unexpected ply layout\n"); return 1; }

    // 逐点读 15 B
    std::vector<Pt> pts(n);
    std::vector<uint8_t> buf(15 * 65536);
    size_t done = 0;
    while (done < n) {
        const size_t want = std::min((size_t)65536, n - done);
        if (std::fread(buf.data(), 15, want, f) != want) {
            std::fprintf(stderr, "short read at %zu\n", done); return 1;
        }
        for (size_t i = 0; i < want; ++i) {
            const uint8_t* q = buf.data() + 15 * i;
            Pt p;
            std::memcpy(&p.x, q + 0, 4);
            std::memcpy(&p.y, q + 4, 4);
            std::memcpy(&p.z, q + 8, 4);
            // 与 bench 的 unpack4x8unorm 对齐:低字节 = r
            p.rgba = (uint32_t)q[12] | ((uint32_t)q[13] << 8) |
                     ((uint32_t)q[14] << 16) | (255u << 24);
            pts[done + i] = p;
        }
        done += want;
    }
    std::fclose(f);

    // 统计
    double lo[3] = {1e300, 1e300, 1e300}, hi[3] = {-1e300, -1e300, -1e300};
    double sum[3] = {0, 0, 0};
    size_t nonfinite = 0;
    for (const Pt& p : pts) {
        const double v[3] = {p.x, p.y, p.z};
        if (!std::isfinite(v[0]) || !std::isfinite(v[1]) || !std::isfinite(v[2])) {
            ++nonfinite; continue;
        }
        for (int k = 0; k < 3; ++k) {
            lo[k] = std::min(lo[k], v[k]); hi[k] = std::max(hi[k], v[k]);
            sum[k] += v[k];
        }
    }
    double ext[3], diag = 0;
    for (int k = 0; k < 3; ++k) { ext[k] = hi[k] - lo[k]; diag += ext[k] * ext[k]; }
    diag = std::sqrt(diag);
    std::printf("non-finite      : %zu\n", nonfinite);
    std::printf("bbox lo         : %.4f %.4f %.4f\n", lo[0], lo[1], lo[2]);
    std::printf("bbox hi         : %.4f %.4f %.4f\n", hi[0], hi[1], hi[2]);
    std::printf("extent          : %.4f %.4f %.4f   diag %.4f\n",
                ext[0], ext[1], ext[2], diag);
    std::printf("centroid        : %.4f %.4f %.4f\n",
                sum[0] / n, sum[1] / n, sum[2] / n);
    int ord[3] = {0, 1, 2};
    std::sort(ord, ord + 3, [&](int a, int b) { return ext[a] < ext[b]; });
    std::printf("axes small->big : %d %d %d\n", ord[0], ord[1], ord[2]);

    // 聚簇程度:体素占用率。均匀分布会接近 100%(在点数 >> 体素数时)。
    for (int vg : {64, 128, 256}) {
        std::unordered_set<uint64_t> occ;
        occ.reserve(pts.size() / 4);
        for (const Pt& p : pts) {
            const double v[3] = {p.x, p.y, p.z};
            uint64_t q[3];
            bool bad = false;
            for (int k = 0; k < 3; ++k) {
                if (!std::isfinite(v[k]) || ext[k] <= 0) { bad = true; break; }
                double t = (v[k] - lo[k]) / ext[k] * (vg - 1e-9);
                q[k] = (uint64_t)std::min(std::max(t, 0.0), (double)vg - 1);
            }
            if (!bad) occ.insert((q[0] * vg + q[1]) * vg + q[2]);
        }
        std::printf("  %3d^3 voxels  : occupied %zu / %d = %.2f%%  "
                    "(%.1f pts per occupied voxel)\n",
                    vg, occ.size(), vg * vg * vg,
                    100.0 * occ.size() / (double)(vg * vg * vg),
                    pts.size() / (double)occ.size());
    }

    // 校验和(u64 求和 + XOR 折叠):后面用来证明「重排确实是个置换」。
    uint64_t xr = 0, sm = 0;
    for (const Pt& p : pts) {
        uint64_t h;
        uint32_t bx, by, bz;
        std::memcpy(&bx, &p.x, 4); std::memcpy(&by, &p.y, 4); std::memcpy(&bz, &p.z, 4);
        h = (uint64_t)bx * 0x9E3779B97F4A7C15ull ^
            (uint64_t)by * 0xC2B2AE3D27D4EB4Full ^
            (uint64_t)bz * 0x165667B19E3779F9ull ^
            (uint64_t)p.rgba * 0x27D4EB2F165667C5ull;
        xr ^= h; sm += h;
    }
    std::printf("checksum        : xor=%016llx sum=%016llx\n",
                (unsigned long long)xr, (unsigned long long)sm);

    FILE* o = std::fopen(out, "wb");
    if (!o) { std::fprintf(stderr, "open %s failed\n", out); return 1; }
    std::fwrite(pts.data(), sizeof(Pt), pts.size(), o);
    std::fclose(o);
    std::printf("wrote %s : %zu points, %zu bytes\n",
                out, pts.size(), pts.size() * sizeof(Pt));
    return 0;
}
