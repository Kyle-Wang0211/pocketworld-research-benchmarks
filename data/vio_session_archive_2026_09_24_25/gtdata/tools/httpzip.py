"""Seekable read-only file over HTTP Range requests (for listing a remote zip's central directory
and pulling small members without downloading the archive)."""
import io
import time
import urllib.request


class HttpFile(io.RawIOBase):
    def __init__(self, url, block=1 << 20):
        self.url = url
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=60) as r:
            self.size = int(r.headers["Content-Length"])
        self.pos = 0
        self.block = block
        self.cache = {}
        self.fetched = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def _blk(self, i):
        if i not in self.cache:
            a = i * self.block
            b = min(self.size, a + self.block) - 1
            req = urllib.request.Request(self.url, headers={"Range": f"bytes={a}-{b}"})
            for attempt in range(8):
                try:
                    with urllib.request.urlopen(req, timeout=120) as r:
                        d = r.read()
                    if len(d) != b - a + 1:
                        raise IOError(f"short range read {len(d)} != {b - a + 1}")
                    self.cache[i] = d
                    break
                except Exception as e:  # transient network errors: retry
                    if attempt == 7:
                        raise
                    time.sleep(2 * (attempt + 1))
            self.fetched += len(self.cache[i])
            if len(self.cache) > 64:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[i]

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        out = bytearray()
        while n > 0:
            i = self.pos // self.block
            blk = self._blk(i)
            o = self.pos - i * self.block
            chunk = blk[o:o + n]
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)
