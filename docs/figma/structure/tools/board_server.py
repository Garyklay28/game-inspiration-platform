"""스크래치 폴더를 서비스하고, POST /save?name=파일명 으로 받은 바이트를 상위 폴더(docs/figma/structure/)에 저장하는 로컬 서버."""
import http.server, os, re, sys, urllib.parse
ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(ROOT)  # docs/figma/structure/

class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)
    def do_POST(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        name = os.path.basename(q.get("name", [""])[0])
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}\.(svg|png)", name):
            self.send_response(400); self.end_headers(); return
        data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        with open(os.path.join(OUT, name), "wb") as f:
            f.write(data)
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
