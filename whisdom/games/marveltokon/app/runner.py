"""
Drop-a-match runner — the app runs the perception pipeline on a capture.

    POST /api/replay/run {"video": "Vid1"}   → runs in a background thread
    GET  /api/jobs                            → {video: {step, done, total, log, error, finished}}

Steps, in order, each a subprocess of the existing CLIs so their behaviour is
exactly the documented one:
    1. replay_intake VID --scan           classify the capture → VID-segments.json
    2. replay_intake VID --read           read every segment → VID-NN.json
    3. find_openings VID                  free-time windows → VID-openings.json
    4. name plates (in-process)           the plate voted across five moments of
                                          each usable segment (read_plates); the
                                          counts are kept in _seen, so a tag
                                          mid-segment shows as two names
Not run: the Punish! caption pass. The dataset's ten reads came from a session
driver that was never turned into a CLI (T-031). New captures show openings
and characters; the Punish! count shows "not run".

Needs ffmpeg, numpy and OpenCV in the Python that runs the server. If they are
missing the job fails on step 1 or 4 and the error is shown in the UI.
"""
import datetime
import json
import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.normpath(os.path.join(HERE, ".."))                      # whisdom/games/marveltokon
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))   # repo root
DATA = os.path.join(PKG, "data")
JOBS = os.path.join(DATA, "app", "jobs.json")
_lock = threading.Lock()


def videos():
    """Capture files the runner can see: *.mp4 in the repo root (gitignored) and the drive."""
    out = []
    for d in (ROOT, os.path.expanduser("~/mnt/Untitled/PS5/CREATE/Video Clips"), "/Volumes/Untitled/PS5/CREATE/Video Clips"):
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.lower().endswith(".mp4"):
                    stem = f[:-4]
                    out.append({"video": stem, "path": os.path.join(d, f), "bytes": os.path.getsize(os.path.join(d, f)),
                                "analysed": os.path.exists(os.path.join(DATA, "replays", stem + "-segments.json"))})
    return out


def _read():
    if os.path.exists(JOBS):
        try:
            return json.load(open(JOBS, encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def _write(j):
    os.makedirs(os.path.dirname(JOBS), exist_ok=True)
    tmp = JOBS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(j, f, indent=1)
    os.replace(tmp, JOBS)


def _set(video, **kv):
    with _lock:
        j = _read()
        e = j.setdefault(video, {"step": "", "done": 0, "total": 5, "log": [], "error": None, "finished": None, "started": None})
        for k, v in kv.items():
            if k == "log":
                e["log"].append("%s %s" % (datetime.datetime.now().strftime("%H:%M:%S"), v))
                e["log"] = e["log"][-60:]
            else:
                e[k] = v
        _write(j)


def running(video):
    e = _read().get(video)
    return bool(e and e.get("started") and not e.get("finished"))


def _cli(first_arg, video, args, step, done):
    _set(video, step=step, done=done, log="start " + step)
    cmd = [sys.executable, "-m", "whisdom.games.marveltokon.extract." + args[0], first_arg] + args[1:]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    tail = (p.stdout or "").strip().splitlines()[-3:]
    for line in tail:
        _set(video, log=line[:160])
    if p.returncode != 0:
        raise RuntimeError(step + ": " + (p.stderr or "").strip()[-400:])


def _nameplates(video):
    sys.path.insert(0, os.path.join(PKG, "extract"))
    import nameplate as N  # noqa: E402
    tpl = N.load_plate_templates()
    rep = os.path.join(DATA, "replays")
    segf = os.path.join(rep, video + "-segments.json")
    segs = json.load(open(segf, encoding="utf-8")).get("segments") or []
    src = next((v["path"] for v in videos() if v["video"] == video), None)
    n = 0
    for i, (a, b) in enumerate(segs):
        pf = os.path.join(rep, "%s-%02d.json" % (video, i))
        if not os.path.exists(pf):
            continue
        r = json.load(open(pf, encoding="utf-8"))
        if (r.get("active_seconds") or 0) < 15:
            continue
        got = N.read_plates(src, a, b, tpl)
        if not got.get("_reads"):
            continue
        r["characters"] = {"L": got.get("L"), "R": got.get("R"), "_seen": got.get("_seen"),
                           "_source": "point character voted from the name plate at five moments through the segment "
                                      "(nameplate.read_plates); 38 of 50 plates in the by-eye set, none wrong. "
                                      "More than one name on a side in _seen means a tag happened mid-segment."}
        with open(pf, "w", encoding="utf-8") as f:
            json.dump(r, f)
        n += 1
    _set(video, log="name plates read on %d segments" % n)


def run(video):
    src = next((v["path"] for v in videos() if v["video"] == video), None)
    if not src:
        _set(video, error="no such capture", finished=datetime.datetime.now().isoformat(timespec="seconds"))
        return
    # CHECK THE MACHINE BEFORE SPENDING FOUR MINUTES ON IT. Without this the first
    # sign of a missing ffmpeg is a traceback partway through step 1.
    try:
        import doctor
        why = doctor.gate("replay")
    except Exception:
        why = None
    if why:
        _set(video, error=why, step="cannot run here", finished=datetime.datetime.now().isoformat(timespec="seconds"), log=why)
        return
    _set(video, started=datetime.datetime.now().isoformat(timespec="seconds"), finished=None, error=None, step="queued", done=0)
    try:
        _cli(src, video, ["replay_intake", "--scan"], "1/5 classify", 0)
        _cli(src, video, ["replay_intake", "--read"], "2/5 read panels", 1)
        _cli(video, video, ["find_openings"], "3/5 openings", 2)   # find_openings takes the stem, not the path
        _set(video, step="4/5 name plates", done=3, log="start name plates")
        _nameplates(video)
        # 5: the receipt videos. A finding without its clip is a claim without its
        # footage — the Review deck showed an error box for every new capture until
        # this step existed (2026-09-02, Raah: "i cannot have this anymore").
        _set(video, step="5/5 clips", done=4, log="start clips")
        pc = subprocess.run([sys.executable, "-m", "whisdom.games.marveltokon.app.clips", video],
                            cwd=ROOT, capture_output=True, text=True)
        for line in (pc.stdout or "").strip().splitlines()[-2:]:
            _set(video, log=line[:160])
        if pc.returncode != 0:
            raise RuntimeError("clips: " + (pc.stderr or "").strip()[-400:])
        _set(video, step="done", done=5, log="done", finished=datetime.datetime.now().isoformat(timespec="seconds"))
    except Exception as e:  # noqa
        _set(video, error=str(e)[:600], step="failed", finished=datetime.datetime.now().isoformat(timespec="seconds"), log="FAILED " + str(e)[:160])


def start(video):
    if running(video):
        return False
    threading.Thread(target=run, args=(video,), daemon=True).start()
    return True


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "Vid1")
    print(json.dumps(_read().get(sys.argv[1] if len(sys.argv) > 1 else "Vid1"), indent=1))
