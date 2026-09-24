# Static file server with CORS so one page can fetch chunks over several SSH tunnels in parallel.
import http.server, socketserver, sys, os
os.chdir(sys.argv[1]); PORT = int(sys.argv[2])
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()
    def log_message(self, *a): pass
class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True; allow_reuse_address = True
S(("127.0.0.1", PORT), H).serve_forever()
