"""
The local app.

Deliberately a stdlib HTTP server serving one HTML file, not Electron or Tauri.
Reasons that matter for this project specifically:

  * No new toolchain. The agent is Python; the app is Python. Raah is on macOS
    and his partner is on Windows, and neither needs Node or Rust installed to
    run it.
  * It stays local. Binds to 127.0.0.1 only, no accounts, no network calls. That
    IS the free tier as described, not a cut-down version of a cloud product.
  * The UI reads match documents through a small JSON API. It never touches the
    parser, so replacing this front end later costs nothing.

The API is deliberately thin — list, detail, review, media. Anything that needs
real work (ingesting, pairing a recording) stays in the CLI, because those are
long-running and better watched in a terminal than in a spinner.
"""
import json
import mimetypes
import os
import posixpath
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))


def _doc_summary(doc):
    """The shape the UI needs, computed once here rather than in JavaScript."""
    m = doc["match"]
    fps = m.get("fps") or 60
    players = []
    for p in doc["players"]:
        ch = p.get("character") or {}
        players.append(dict(slot=p["slot"], name=p.get("display_name"),
                            character=ch.get("name"),
                            outcome=(m.get("outcome") or {}).get(str(p["slot"]))))
    kos = [dict(slot=x.get("slot"), seconds=round(x["frame"] / fps, 1))
           for x in doc.get("analysis", {}).get("moments", []) if x.get("kind") == "ko"]
    dmg = {}
    for d in doc.get("observations", {}).get("damage", []):
        dmg.setdefault(str(d["slot"]), []).append([d["seconds"], d["estimate"]])
    return dict(
        id=m["id"], patch=m.get("patch"), level=m.get("level_name"),
        duration=round((m.get("duration_frames") or 0) / fps, 1),
        source=m.get("source_file"), fps=fps,
        has_video=bool(dmg), video_path=m.get("video_path"),
        video_offset=(m.get("video_offset_frames") or 0) / float(fps),
        outcome_source=m.get("outcome_source"),
        players=players, kos=sorted(kos, key=lambda k: k["seconds"]), damage=dmg,
        inputs=len(doc.get("observations", {}).get("inputs", [])),
    )


class Handler(BaseHTTPRequestHandler):
    store = None
    adapter_name = "brawlhalla"

    def log_message(self, *a):
        pass                      # quiet; the CLI prints what matters

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass                  # browser cancelled a video range request

    def _file(self, path, ctype=None):
        if not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ctype = ctype or mimetypes.guess_type(path)[0] or "application/octet-stream"
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        # Video needs range support or Safari refuses to play it at all.
        if rng and rng.startswith("bytes="):
            try:
                s, _, e = rng[6:].partition("-")
                start = int(s) if s else 0
                end = int(e) if e else size - 1
            except ValueError:
                start, end = 0, size - 1
            end = min(end, size - 1)
            with open(path, "rb") as f:
                f.seek(start)
                chunk = f.read(end - start + 1)
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.send_header("Content-Length", str(len(chunk)))
            self.end_headers()
            try:
                self.wfile.write(chunk)
            except BrokenPipeError:
                pass
            return
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        one = lambda k, d=None: (q.get(k) or [d])[0]
        p = u.path

        if p in ("/", "/index.html"):
            return self._file(os.path.join(HERE, "index.html"), "text/html")

        if p == "/api/facets":
            f = self.store.facets()
            f["players"] = [dict(name=r["display_name"], n=r["n"])
                            for r in self.store.players_seen(40)]
            return self._send(200, f)

        if p == "/api/matches":
            hv = one("video")
            rows = self.store.list_matches(
                player=one("player"), patch=one("patch"), q=one("q"),
                has_video=(None if hv in (None, "", "any") else hv == "1"),
                limit=int(one("limit", 100)), offset=int(one("offset", 0)))
            out = []
            for r in rows:
                d = dict(r)
                d["duration"] = round((d.get("duration_frames") or 0) /
                                      float(d.get("fps") or 60), 1)
                out.append(d)
            return self._send(200, out)

        if p.startswith("/api/match/"):
            mid = posixpath.basename(p)
            doc = self.store.load(mid)
            if not doc:
                return self._send(404, {"error": "no such match"})
            return self._send(200, _doc_summary(doc))

        if p.startswith("/api/review/"):
            mid = posixpath.basename(p)
            doc = self.store.load(mid)
            if not doc:
                return self._send(404, {"error": "no such match"})
            from whisdom.agent.review import review_match
            try:
                rev = review_match(doc, one("player"))
            except Exception as e:
                return self._send(200, {"error": str(e)})
            if not rev:
                return self._send(200, {"error": "no KOs to review in this match"})
            from whisdom.games.brawlhalla.payoffs import ATK_OPTIONS
            lbl = dict(ATK_OPTIONS)
            rev["tendency"] = [dict(key=k, label=lbl.get(k, k), share=v)
                               for k, v in sorted(rev["tendency"].items(),
                                                  key=lambda kv: -kv[1])]
            return self._send(200, rev)

        if p == "/media":
            # Only ever serves the recording a match document points at.
            mid = one("match")
            doc = self.store.load(mid) if mid else None
            path = (doc or {}).get("match", {}).get("video_path")
            if not path:
                return self._send(404, {"error": "no recording paired with this match"})
            return self._file(path)

        return self._send(404, {"error": "not found"})


def serve(store, host="127.0.0.1", port=8756, open_browser=True):
    Handler.store = store
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = "http://%s:%d/" % (host, port)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    return httpd, url
