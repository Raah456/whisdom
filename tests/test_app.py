"""
The local app's API contract.

The UI is plain JavaScript reading these endpoints, so a shape change here breaks
the app silently. These checks pin the contract.

    python3 tests/test_app.py
"""
import json, os, sys, threading, time, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STORE = os.environ.get("WHISDOM_STORE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "store")


def check(name, ok, detail=""):
    print("   %-52s %s%s" % (name, "ok" if ok else "FAIL", "  " + detail if detail else ""))
    return 0 if ok else 1


def run(store_path=STORE):
    if not os.path.isdir(store_path):
        print("SKIPPED — no store. Run `whisdom ingest` first, or set WHISDOM_STORE.\n"
              "         This is a SKIP, not a pass.")
        return 0
    from whisdom.agent.store import Store
    from whisdom.app.server import serve
    st = Store(store_path)
    httpd, url = serve(st, port=8799, open_browser=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.4)
    base = url.rstrip("/")
    g = lambda p: json.loads(urllib.request.urlopen(base + p).read())
    fails = 0
    try:
        f = g("/api/facets")
        fails += check("facets has the counts the UI shows",
                       all(k in f for k in ("total", "with_video", "with_kos", "patches", "players")))
        ms = g("/api/matches")
        fails += check("match list is a list", isinstance(ms, list) and len(ms) > 0)
        need = {"match_id", "who", "has_video", "patch", "duration"}
        fails += check("match rows carry what the list renders",
                       need <= set(ms[0]), str(sorted(need - set(ms[0]))) if need - set(ms[0]) else "")
        mid = ms[0]["match_id"]
        d = g("/api/match/" + mid)
        need = {"id", "players", "kos", "damage", "has_video", "duration", "inputs", "video_offset"}
        fails += check("match detail carries what the page renders", need <= set(d))
        fails += check("players carry slot, name, character",
                       all({"slot", "name", "character"} <= set(p) for p in d["players"]))
        # thread safety: the server hands each request its own thread
        errs = []
        def hit():
            try: g("/api/facets")
            except Exception as e: errs.append(e)
        ts = [threading.Thread(target=hit) for _ in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        fails += check("concurrent requests do not break sqlite", not errs,
                       str(errs[0])[:60] if errs else "")
        r = g("/api/review/" + mid)
        if "error" not in r:
            fails += check("review carries deaths and tendency",
                           {"deaths", "tendency", "player", "opponent"} <= set(r))
            fails += check("tendency is UI-shaped (label + share)",
                           all({"label", "share"} <= set(t) for t in r["tendency"]))
        # unknown ids must 404, not 500
        code = None
        try: urllib.request.urlopen(base + "/api/match/nope")
        except urllib.error.HTTPError as e: code = e.code
        fails += check("unknown match returns 404", code == 404, "got %s" % code)
        # the app must not serve arbitrary files
        code = None
        try: urllib.request.urlopen(base + "/media?match=nope")
        except urllib.error.HTTPError as e: code = e.code
        fails += check("media refuses unknown matches", code == 404, "got %s" % code)
        html = urllib.request.urlopen(base + "/").read().decode()
        fails += check("index page serves", "<title>Whisdom</title>" in html)
    finally:
        httpd.shutdown()
    print("app: %d check(s) failed" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else STORE))
