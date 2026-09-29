"""Turn a long capture into per-segment replay-playback records.

A session recording is not one thing. LongBatch1.mp4 is 54 minutes containing
online matches, lobbies, a network error, menus, character art AND replay
playback with the analysis overlay up. Only the last of those is worth reading:
playback is deterministic local simulation, so unlike live online footage it
carries no rollback and its frame numbers mean something.

So step one is honest classification, and step one has a trap in it. The first
attempt scored "is there a bright colourless plate here" and fired on 90% of the
capture, live matches included, because the panel is SEMI-TRANSPARENT and any
pale stage background looks like it. What is actually invariant is the panel's
LABEL BLOCK - the words Damage / Combo / Highest Combo, dark text at a fixed
position. High-pass the crop to throw the background tint away, correlate
against a template cut from a confirmed frame, and the separation is not close:

    overlay frames   +0.979 .. +1.000
    everything else  -0.028 .. +0.057

Usage:
    python replay_intake.py VID --scan                 # -> segments, prints a map
    python replay_intake.py VID --read [--seg N]       # -> records/<stem>-NN.json
    python replay_intake.py VID --template T           # recut the label template
"""
import json
import pathlib
import subprocess
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import replay_hud as R              # noqa: E402

W, H = 1920, 1080
LABEL_BOX = (245, 228, 190, 96)     # keep w and h EVEN: ffmpeg silently rounds a
                                    # crop down and returns the short buffer with
                                    # no error, which reads as "no frame".
LABEL_TPL = HERE / "overlay_label_tpl.npy"
ON = 0.5                            # anything between 0.06 and 0.97 never happens


# --------------------------------------------------------------- sampling ---
def _gray_crop(video, t, box):
    x, y, w, h = box
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
         "-vf", f"crop={w}:{h}:{x}:{y}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True)
    if len(p.stdout) < w * h:
        return None
    return np.frombuffer(p.stdout[:w * h], np.uint8).reshape(h, w).astype(np.float32)


def highpass(a, k=9):
    """Subtract a box blur. Kills the panel's background-dependent tint and
    leaves the text strokes, which are the only part that never changes."""
    pad = np.pad(a, k // 2, mode="edge")
    c = np.pad(np.cumsum(np.cumsum(pad, 0), 1), ((1, 0), (1, 0)))
    h, w = a.shape
    blur = (c[k:k+h, k:k+w] - c[:h, k:k+w] - c[k:k+h, :w] + c[:h, :w]) / (k * k)
    d = a - blur
    return (d - d.mean()) / (d.std() + 1e-6)


def cut_template(video, t, out=LABEL_TPL):
    a = _gray_crop(video, t, LABEL_BOX)
    if a is None:
        raise SystemExit(f"no frame at t={t}")
    np.save(out, highpass(a))
    return out


def overlay_score(video, t, tpl):
    a = _gray_crop(video, t, LABEL_BOX)
    return None if a is None else float((highpass(a) * tpl).mean())


def duration(video):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", video], capture_output=True, text=True)
    return float(p.stdout.strip())


def scan(video, step=5.0, t0=0.0, t1=None, tpl=None):
    """[(t, score)] across the capture. Bounded work per call on purpose: the
    device bridge caps a command at ~45 s and kills background jobs when the
    call returns, so this is designed to be run in slices and merged."""
    tpl = np.load(LABEL_TPL) if tpl is None else tpl
    t1 = duration(video) if t1 is None else t1
    out, t = [], t0
    while t < t1:
        out.append((round(t, 1), overlay_score(video, t, tpl)))
        t += step
    return out


def segments(scored, step=5.0, min_len=20.0, trim=2.5):
    """Contiguous overlay stretches. Trimmed inward by one half-step at each end
    because a boundary sample only bounds the transition to within `step`, and a
    sample taken during the fade reads as neither one thing nor the other."""
    segs, start, prev = [], None, None
    for t, s in scored:
        on = s is not None and s > ON
        if on and start is None:
            start = t
        elif not on and start is not None:
            segs.append((start, prev + step))
            start = None
        if on:
            prev = t
    if start is not None:
        segs.append((start, prev + step))
    out = []
    for a, b in segs:
        a, b = a + trim, b - trim
        if b - a >= min_len:
            out.append((round(a, 1), round(b, 1)))
    return out


# ---------------------------------------------------------------- reading ---
def frames(video, a, b, fps):
    """Decode a span once, sequentially, yielding (t, bgr).

    Seeking per frame costs ~130 ms; one sequential pass over the same span is
    far cheaper, and a segment is short enough to fit a single call."""
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", video,
         "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE)
    n, i = W * H * 3, 0
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield a + i / fps, np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        i += 1
    p.stdout.close()
    p.wait()


def read_segment(video, a, b, fps=10.0, ptpl=None, dtpl=None):
    """One segment -> samples of both sides' panel and input column.

    Nothing here guesses. A field that cannot be read confidently is null, and
    downstream code must treat null as "unknown", never as zero."""
    ptpl = R.load_templates(R.PANEL_TEMPLATES) if ptpl is None else ptpl
    dtpl = R.load_templates() if dtpl is None else dtpl
    samples = []
    for t, img in frames(video, a, b, fps):
        samples.append({
            "t": round(t, 3),
            "L": R.panel_data(img, "L", ptpl),
            "R": R.panel_data(img, "R", ptpl),
            "Li": [r["frames"] for r in R.input_rows(img, "L", dtpl)],
            "Ri": [r["frames"] for r in R.input_rows(img, "R", dtpl)],
        })
    return samples


FREEZE_S = 3.0          # a hold this long is a paused replay, not neutral


def mark_frozen(samples, hold=FREEZE_S):
    """Flag samples where the replay is PAUSED, in place.

    The overlay stays up when playback is paused, so the label template still
    matches and the segment scan happily calls it usable. One 95-second stretch
    of this capture is a single frozen frame and would otherwise contribute a
    fictional 95 seconds of "gameplay" to any rate the coach computes.

    Exact-signature comparison does NOT work here: a third of the fields read as
    null on any given frame, and that jitter makes a motionless picture look
    like it is changing. So a sample continues the current hold unless it
    CONTRADICTS it — some field where both the sample and the accumulated
    reading are known and they differ. Null is not evidence of change.

    During real play something always ticks: the Total counter runs through a
    move, damage and combo update on contact. A neutral standoff can hold for a
    beat, which is why the threshold is three seconds rather than one.
    """
    keys = [(k, f) for k in ("L", "R") for f in R.FIELDS]
    n, i = len(samples), 0
    while i < n:
        known = {kf: samples[i][kf[0]][kf[1]] for kf in keys}
        j = i
        while j + 1 < n:
            nxt = samples[j + 1]
            if any(known[kf] is not None and nxt[kf[0]][kf[1]] is not None
                   and known[kf] != nxt[kf[0]][kf[1]] for kf in keys):
                break
            for kf in keys:
                if known[kf] is None:
                    known[kf] = nxt[kf[0]][kf[1]]
            j += 1
        held = samples[j]["t"] - samples[i]["t"]
        for k in range(i, j + 1):
            samples[k]["frozen"] = held >= hold
        i = j + 1
    return samples


def active_seconds(samples, fps):
    return sum(1 for s in samples if not s.get("frozen")) / fps


def moves(samples, side):
    """Collapse samples into one entry per move shown for `side`.

    WHAT THE PANEL ACTUALLY IS — this cost a wrong first implementation, so it
    is written down. The panel is not a static frame-data readout. It is a LIVE
    METER. Sampling at 10 Hz on 59.94 fps footage, `Total` reads 66, 72, 78 on
    consecutive samples: +6 each time, which is +1 per game frame. `Active` and
    `Recovery` tick the same way. They are counters of frames elapsed, and they
    reset when a new move starts.

    `Attack Startup` is the exception and the only static property on display:
    it holds steady for the whole move and changes when the move changes.

    Keying move identity on (startup, active, total) therefore produced 256
    "moves" in 45 seconds — one every other sample, which is not a thing that
    can happen. The identity is `Attack Startup`, plus a reset of the `Total`
    counter to catch two different moves that happen to share a startup value.

    Because the counters tick, the meaningful value for a completed move is the
    LAST one seen before the reset, so `active` and `total` here are maxima over
    the run — with the caveat that a move ending between two samples is observed
    up to 5 frames short. Treat them as lower bounds, not measurements.

    A field that could not be read is null and stays null; unknown is never
    silently turned into zero.
    """
    out = []
    for s in samples:
        if s.get("frozen"):
            continue
        p = s[side]
        su, tot = p["Attack Startup"], p["Total"]
        if su is None and tot is None:
            continue
        cur = out[-1] if out else None
        same = (cur is not None
                and (su is None or cur["startup"] is None or su == cur["startup"])
                and not (tot is not None and cur["total"] is not None
                         and tot < cur["total"]))          # counter reset = new move
        if same:
            cur["until"] = s["t"]
            cur["samples"] += 1
            if cur["startup"] is None:
                cur["startup"] = su
            for src, dst in (("Active", "active"), ("Total", "total")):
                if p[src] is not None:
                    cur[dst] = p[src] if cur[dst] is None else max(cur[dst], p[src])
            for f in ("Damage", "Combo", "Highest Combo", "Recovery"):
                if p[f] is not None:
                    cur[f.lower().replace(" ", "_")] = p[f]
            continue
        out.append({"t": s["t"], "until": s["t"], "samples": 1,
                    "startup": su, "active": p["Active"], "total": tot,
                    "damage": p["Damage"], "combo": p["Combo"],
                    "highest_combo": p["Highest Combo"], "recovery": p["Recovery"]})
    return out


# -------------------------------------------------------------------- cli ---
def records_dir(video):
    d = HERE.parent / "data" / "replays"
    d.mkdir(parents=True, exist_ok=True)
    return d


def main():
    video = sys.argv[1]
    args = sys.argv[2:]
    stem = pathlib.Path(video).stem
    segfile = records_dir(video) / f"{stem}-segments.json"

    if "--template" in args:
        t = float(args[args.index("--template") + 1])
        print("template ->", cut_template(video, t))
        return

    if "--scan" in args:
        t0 = float(args[args.index("--from") + 1]) if "--from" in args else 0.0
        t1 = float(args[args.index("--to") + 1]) if "--to" in args else None
        scored = scan(video, t0=t0, t1=t1)
        prev = json.loads(segfile.read_text())["scored"] if segfile.exists() else []
        merged = {t: s for t, s in prev}
        merged.update({t: s for t, s in scored})
        scored = sorted(merged.items())
        segs = segments(scored)
        segfile.write_text(json.dumps({"video": stem, "scored": scored,
                                       "segments": segs}, indent=1))
        print(f"{len(scored)} samples, {len(segs)} segments, "
              f"{sum(b-a for a,b in segs):.0f}s usable -> {segfile.name}")
        return

    if "--read" in args:
        meta = json.loads(segfile.read_text())
        segs = meta["segments"]
        if "--seg" in args:
            spec = args[args.index("--seg") + 1]
            which = ([int(spec)] if "-" not in spec
                     else range(int(spec.split("-")[0]), int(spec.split("-")[1]) + 1))
        else:
            which = range(len(segs))
        fps = float(args[args.index("--fps") + 1]) if "--fps" in args else 10.0
        ptpl, dtpl = R.load_templates(R.PANEL_TEMPLATES), R.load_templates()
        for i in which:
            a, b = segs[i]
            samples = mark_frozen(read_segment(video, a, b, fps, ptpl, dtpl))
            act = active_seconds(samples, fps)
            two_sided = any(s["R"][f] is not None for s in samples for f in R.FIELDS)
            rec = {"video": stem, "segment": i, "start": a, "end": b,
                   "sample_fps": fps, "active_seconds": round(act, 1),
                   "two_sided": two_sided, "samples": samples,
                   "moves": {"L": moves(samples, "L"), "R": moves(samples, "R")}}
            out = records_dir(video) / f"{stem}-{i:02d}.json"
            out.write_text(json.dumps(rec))
            nn = sum(1 for s in samples for k in ("L", "R")
                     for v in s[k].values() if v is None)
            tot = len(samples) * 14
            flag = "" if two_sided else "  ONE-SIDED"
            print(f"seg {i:2d}  {a:7.1f}-{b:7.1f}s  {act:5.1f}s live of {b-a:5.1f}s  "
                  f"L{len(rec['moves']['L']):3d}/R{len(rec['moves']['R']):3d} moves  "
                  f"{nn/max(tot,1)*100:4.1f}% unread{flag}")
        return

    print(__doc__)


if __name__ == "__main__":
    main()
