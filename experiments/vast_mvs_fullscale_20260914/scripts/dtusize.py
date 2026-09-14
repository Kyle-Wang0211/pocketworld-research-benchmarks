import urllib.request
for n in ("Rectified","Cleaned","Points","SampleSet","Surfaces"):
    try:
        r = urllib.request.Request("http://roboimagedata2.compute.dtu.dk/data/MVS/%s.zip" % n, method="HEAD")
        s = int(urllib.request.urlopen(r, timeout=40).headers["Content-Length"])
        print("  %-16s %7.2f GB" % (n + ".zip", s / 1e9))
    except Exception as e:
        print("  %-16s 取不到: %s" % (n, str(e)[:60]))
