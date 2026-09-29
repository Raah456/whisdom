"""Smoke test for the Tōkon app — stdlib only, so it runs on Raah's Mac.

WHY NOT PLAYWRIGHT. The app is checked with a headless browser during a session,
but Playwright is not on the machine that actually runs this app, and a test that
cannot be run by its owner is not a test. This one starts the real server on a
free port, walks every JSON endpoint, and reads the single HTML file for the ids
and functions the code paths depend on. Nothing to install.

    python3 tests/smoke.py            # everything
    python3 tests/smoke.py --quiet    # only the failures
    python3 tests/smoke.py --ui       # also drive a browser, if Playwright is here

Exit code is the number of failures, so it can gate a commit.
"""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "whisdom", "games", "marveltokon", "app")
UI = os.path.join(APP, "ui", "index.html")

FAILS, CHECKS = [], []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok), detail))
    if not ok:
        FAILS.append((name, detail))
    return ok


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def get(base, path, timeout=25):
    try:
        with urllib.request.urlopen(base + path, timeout=timeout) as r:
            body = r.read()
            ct = r.headers.get("content-type", "")
            return r.status, (json.loads(body.decode("utf-8")) if "json" in ct else body), None
    except urllib.error.HTTPError as e:
        return e.code, None, e.reason
    except Exception as e:
        return 0, None, "%s: %s" % (type(e).__name__, str(e)[:120])


# (path, what it must contain — a key, or a callable)
ENDPOINTS = [
    ("/api/health", None),
    ("/api/roster", None),
    ("/api/concepts", None),
    ("/api/knowledge", None),
    ("/api/replays", lambda d: isinstance(d, list)),
    ("/api/videos", lambda d: isinstance(d, list)),
    ("/api/captures", lambda d: "captures" in d and "note" in d),
    ("/api/habits", lambda d: "opponents" in d and "label" in d),
    ("/api/starters/LongBatch1", lambda d: "starters" in d and "known_gap" in d),
    ("/api/doctor", lambda d: "tools" in d and "jobs" in d and "python" in d),
    ("/api/progress", lambda d: "xp" in d),
    ("/api/grades", None),
    ("/api/grade_tags", lambda d: "real" in d and "lag" in d),
    ("/api/tech", None),
    ("/api/drills", None),
    ("/api/audio", None),
    ("/api/sources", lambda d: "sources" in d),
    ("/api/quotes", None),
    ("/api/social/posts", None),
    ("/api/profile", None),
    ("/api/secrets", None),
    ("/api/admin/notes", lambda d: isinstance(d, list)),
    ("/api/jobs", None),
    ("/api/art", None),
    ("/api/matchup?them=Doctor%20Doom&move=2H&you=Magik", None),
]

# ids the UI must still have — each is a screen or a control something else clicks
IDS = ["s-start", "s-menu", "s-team", "s-matchup", "s-know", "s-train", "s-replay",
       "s-comm", "s-opts", "s-bgm", "s-prof", "s-lang", "s-input", "s-keys",
       "mmReplay", "mmOpts", "optMenu", "optPane", "rpMain", "rpSub", "admin"]
# functions the render paths call — a rename that misses one call site is the
# failure this catches
FUNCS = ["renderReplay", "renderProgress", "renderHabits", "renderStarters", "renderCoach", "renderOptPane", "breakdownHtml",
         "reviewHtml", "convHtml", "inputHtml", "arrowSvg", "frameFill", "renderBgm",
         "renderSources", "renderFeed", "wireReview"]


def ui_checks():
    src = open(UI, encoding="utf-8").read()
    check("ui/index.html present", len(src) > 50_000, "%d bytes" % len(src))
    for i in IDS:
        check("id #%s" % i, ('id="%s"' % i) in src)
    for f in FUNCS:
        defined = re.search(r"\b(function\s+%s\b|const\s+%s\s*=)" % (f, f), src)
        check("function %s()" % f, bool(defined))
    # every data-view the Replay tabs offer must have a branch that renders it
    views = set(re.findall(r'data-view="([a-z]+)"', src)) | set(re.findall(r'VIEWS=\["([^\]]+)\]', src) and
                                                               re.findall(r'"([a-z]+)"', re.search(r'VIEWS=\[([^\]]+)\]', src).group(1)) or [])
    for v in sorted(views):
        check("Replay view '%s' has a render path" % v,
              ('RP.view==="%s"' % v) in src or ('%s:' % v) in src)
    # scripts must at least tokenise as one balanced block
    scripts = re.findall(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", src, re.S)
    joined = "\n".join(scripts)
    check("script blocks found", len(scripts) >= 1, "%d blocks, %d chars" % (len(scripts), len(joined)))
    check("braces balanced in script", joined.count("{") == joined.count("}"),
          "%d { vs %d }" % (joined.count("{"), joined.count("}")))
    # no external asset except the font stylesheet (which build 17 wants vendored)
    # the font stylesheet (build 17 wants it vendored) and X's own embed widget are the
    # only two the app is allowed to reach for; anything else is a regression.
    allowed = ("fonts.googleapis", "fonts.gstatic", "platform.twitter.com")
    ext = [u for u in re.findall(r'(?:src|href)="(https?://[^"]+)"', src)
           if not any(a in u for a in allowed)]
    check("no unexpected external assets", not ext, ", ".join(ext[:3]))


def data_checks():
    pkg = os.path.join(ROOT, "whisdom", "games", "marveltokon")
    for rel in ("data/app/concepts.json", "data/verified.json", "data/movenames.json",
                "data/mechanics.json", "data/move_states.json", "data/filefd.json"):
        check("data file %s" % rel, os.path.exists(os.path.join(pkg, rel)))
    rep = os.path.join(pkg, "data", "replays")
    segs = [f for f in os.listdir(rep)] if os.path.isdir(rep) else []
    caps = sorted({f.split("-segments.json")[0] for f in segs if f.endswith("-segments.json")})
    check("at least one analysed capture", bool(caps), ", ".join(caps))
    for v in caps:
        for suffix, needed in (("-segments.json", True), ("-events.json", False),
                               ("-combos.json", False), ("-punishes.json", False)):
            p = os.path.join(rep, v + suffix)
            if needed:
                check("%s%s" % (v, suffix), os.path.exists(p))
            elif os.path.exists(p):
                try:
                    json.load(open(p, encoding="utf-8"))
                    check("%s%s parses" % (v, suffix), True)
                except ValueError as e:
                    check("%s%s parses" % (v, suffix), False, str(e)[:80])


def server_checks(quiet):
    port = free_port()
    env = dict(os.environ, PYTHONPATH=ROOT)
    proc = subprocess.Popen([sys.executable, os.path.join(APP, "server.py"),
                             "--port", str(port), "--no-open"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, text=True)
    base = "http://127.0.0.1:%d" % port
    up = False
    for _ in range(60):
        time.sleep(0.25)
        if proc.poll() is not None:
            break
        code, _, _ = get(base, "/api/health", timeout=2)
        if code == 200:
            up = True
            break
    if not check("server starts", up, (proc.stdout.read()[:400] if proc.poll() is not None else "no /api/health after 15s")):
        try:
            proc.terminate()
        except Exception:
            pass
        return
    try:
        code, body, err = get(base, "/")
        check("GET / serves the app", code == 200 and body and b"<title" in body[:4000], err or "")
        for path, want in ENDPOINTS:
            code, body, err = get(base, path)
            ok = code == 200 and (want is None or (body is not None and want(body)))
            check("GET %s" % path, ok, err or ("shape" if code == 200 else "HTTP %s" % code))
        code, caps, _ = get(base, "/api/replays")
        for c in (caps or [])[:4]:
            code, rep, err = get(base, "/api/replay/" + c["video"])
            ok = code == 200 and rep and "findings" in rep and "you" in rep
            check("GET /api/replay/%s" % c["video"], ok, err or "")
            if ok:
                bad = [f for f in rep["findings"] if not f.get("receipt")]
                check("every finding in %s carries a receipt" % c["video"], not bad,
                      "%d without" % len(bad))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def ui_browser():
    try:
        from playwright.sync_api import sync_playwright  # noqa
    except Exception:
        check("Playwright present (--ui)", False, "not installed — skipped, the rest still ran")
        return
    port = free_port()
    env = dict(os.environ, PYTHONPATH=ROOT)
    proc = subprocess.Popen([sys.executable, os.path.join(APP, "server.py"), "--port", str(port), "--no-open"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    time.sleep(3)
    errs = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1440, "height": 1000})
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto("http://127.0.0.1:%d/" % port)
            pg.wait_for_timeout(900)
            if pg.is_visible("#inMouse"):
                pg.click("#inMouse")
                pg.wait_for_timeout(500)
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(900)
            for screen, btn in (("s-replay", "#mmReplay"), ("s-opts", "#mmOpts")):
                pg.click(btn)
                pg.wait_for_timeout(1800)
                check("browser: %s opens" % screen,
                      pg.evaluate("document.querySelector('.screen.on').id") == screen)
                pg.keyboard.press("Escape")
                pg.wait_for_timeout(600)
            b.close()
    finally:
        proc.terminate()
    check("browser: no page errors", not errs, "; ".join(errs[:2]))


def main():
    quiet = "--quiet" in sys.argv
    ui_checks()
    data_checks()
    server_checks(quiet)
    if "--ui" in sys.argv:
        ui_browser()
    width = max(len(n) for n, _, _ in CHECKS) + 2
    for name, ok, detail in CHECKS:
        if ok and quiet:
            continue
        print("%-4s %-*s %s" % ("ok" if ok else "FAIL", width, name, detail if not ok else detail[:60]))
    print("\n%d checks, %d failed" % (len(CHECKS), len(FAILS)))
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(min(main(), 120))
