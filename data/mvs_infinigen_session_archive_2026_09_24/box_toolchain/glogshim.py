import io
for T in ("base","fss"):
    p = "/root/av_fss/src_%s/src/CMakeLists.txt" % T
    t = io.open(p, encoding="utf-8").read()
    if "[FSS-BUILD]" in t:
        print("already", T); continue
    a = "find_package(Ceres"
    i = t.find(a)
    assert i > 0, "no Ceres find_package in " + p
    ls = t.rfind("\n", 0, i) + 1
    t = t[:ls] + "find_package(glog QUIET)  # [FSS-BUILD] Ubuntu CeresConfig references glog::glog without find_dependency\n" + t[ls:]
    io.open(p, "w", encoding="utf-8").write(t)
    print("patched", T)
