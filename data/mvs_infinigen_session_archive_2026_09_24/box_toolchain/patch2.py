import io,sys
p="/root/av_fss/src_fss/src/aliceVision/fuseCut/GraphFiller.cpp"
t=io.open(p,encoding="utf-8").read()
old="""    ALICEVISION_LOG_INFO("[FSS] interface input points: " << nbInterfaceVertices << ", full tetrahedra: " << nbFull
                                                          << ", weakly-supported full tetrahedra (theta_in < q): " << nbWeak);
"""
new="""    ALICEVISION_LOG_INFO("[FSS] interface input points: " << nbInterfaceVertices << ", full tetrahedra: " << nbFull
                                                          << ", weakly-supported full tetrahedra (theta_in < q): " << nbWeak);

    {
        // diagnostics only: distribution of theta_in over the finite full tetrahedra
        std::vector<float> s;
        s.reserve(nbFull);
        for (CellIndex ci = 0; ci < _cellIsFull.size(); ++ci)
        {
            if (_cellIsFull[ci] && !_tetrahedralization.isInfiniteCell(ci))
                s.push_back(theta[ci]);
        }
        if (!s.empty())
        {
            std::sort(s.begin(), s.end());
            auto q = [&](double f) { return s[std::min(s.size() - 1, (std::size_t)(f * s.size()))]; };
            ALICEVISION_LOG_INFO("[FSS] theta_in percentiles over full tetrahedra: p0=" << s.front()
                << " p1=" << q(0.01) << " p5=" << q(0.05) << " p10=" << q(0.10) << " p25=" << q(0.25)
                << " p50=" << q(0.50) << " p75=" << q(0.75) << " p90=" << q(0.90) << " p99=" << q(0.99)
                << " max=" << s.back());
            std::size_t z = 0;
            for (float v : s) { if (v <= 0.0f) ++z; else break; }
            ALICEVISION_LOG_INFO("[FSS] full tetrahedra with theta_in == 0: " << z << " / " << s.size());
        }
    }
"""
assert t.count(old)==1
t=t.replace(old,new)
if "#include <algorithm>" not in t:
    t=t.replace("#include <cstdlib>","#include <algorithm>\n#include <cstdlib>",1)
io.open(p,"w",encoding="utf-8").write(t)
print("patch2 ok")
