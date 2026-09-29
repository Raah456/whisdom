"""Sweep a capture for the game's own judgement captions — Punish!, Good!, Knockdown!

WHY A CLI. The ten Punish! captions the dataset carries were read by a session
driver that was never written down (T-031), so no new capture could have any. A
capture with openings but no captions cannot be compared to one that has both,
which is the whole point of a second capture.

TWO PASSES, BECAUSE FULL-RES SEEKING IS THE EXPENSIVE PART.
  1. DETECT. One ffmpeg process per segment pipes the caption band (y 655..885)
     at 10 fps, scaled to 480 wide — 83 KB a frame instead of 6 MB — and every
     frame is tested for the teal banner. Teal is unmistakable and survives the
     downscale; this is the cheap half and it runs at many times real time.
  2. READ. Only the frames where the banner is up are fetched at full
     resolution, and caption.read() template-matches the WORD inside it. The
     banner is the container; the word is the meaning (see caption.py).

A run of consecutive detections is ONE caption, not one per frame: the banner
sits on screen for about a second. The event's time is the frame with the most
teal — the banner at its fullest, which is also when the word is most readable.

THE SIDE. x < 960 is the left banner, x >= 960 the right. Settled 2026-08-25
from the player's own takes on all ten: the caption sits on the PUNISHER's side.

KNOWN LIMIT, CARRIED FORWARD. Only Punish!, Good! and Knockdown! are in the
template bank, and only Punish! has been validated by eye. Anything else in the
banner reads "?" and is written down as "?" rather than dropped, so the count of
unread captions is visible instead of silent.
"""
import json
import pathlib
import subprocess
import sys

import numpy as np

import caption as C

HERE = pathlib.Path(__file__).resolve().parent
REPLAYS = HERE.parent / "data" / "replays"

DET_W = 480          # detector width; the band is 1920 wide at full res
DET_FPS = 10.0
MIN_TEAL = 220       # teal pixels at DET_W that count as a banner up
GAP = 0.35           # seconds between detections that still count as one caption


def band_stream(video, a, b, w=DET_W, fps=DET_FPS):
    """(t, teal_pixels) for every sampled frame of the caption band in [a, b]."""
    x, y, bw, bh = C.BAND
    h = max(2, int(round(bh * w / bw / 2)) * 2)
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", "%.3f" % a, "-i", str(video), "-t", "%.3f" % (b - a),
         "-vf", "crop=%d:%d:%d:%d,scale=%d:%d,fps=%s" % (bw, bh, x, y, w, h, fps),
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = w * h * 3
    i = 0
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        fr = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        yield a + i / fps, int(C.teal(fr).sum())
        i += 1
    p.stdout.close()
    p.wait()


def events(stream, min_teal=MIN_TEAL, gap=GAP):
    """Runs of frames with the banner up -> one event each, timed at peak teal."""
    out, cur = [], None
    for t, v in stream:
        if v >= min_teal:
            if cur and t - cur["last"] <= gap:
                cur["last"] = t
                if v > cur["peak"]:
                    cur["peak"], cur["t"] = v, t
            else:
                if cur:
                    out.append(cur)
                cur = {"t0": t, "t": t, "last": t, "peak": v}
        elif cur and t - cur["last"] > gap:
            out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    for e in out:
        e["span"] = round(e["last"] - e["t0"], 2)
    return out


MAX_DIST = 0.17      # a word bitmap this far from a template is not that word
MIN_MARGIN = 0.020   # ...and must beat the next word by this much
PER_EVENT = 5        # full-res frames read inside one banner event


def rank(img, tpl):
    """[(x0, distance, word, margin)] for every banner on screen, unthresholded."""
    out = []
    for span in C.banners(img):
        bm = C.word_bitmap(img, span)
        if bm is None:
            continue
        ranked = sorted((float(np.abs(bm - t).mean()), k) for k, t in tpl.items())
        d0, w0 = ranked[0]
        d1 = ranked[1][0] if len(ranked) > 1 else 9.9
        out.append((int(span[0]), d0, w0, d1 - d0))
    return out


def read_event(video, e, tpl, n=PER_EVENT):
    """The best read of each side across several frames of one banner event.

    ONE FRAME IS NOT ENOUGH, and the frame with the most teal is not the right
    one. The banner animates: it is widest (peak teal) while the word is still
    sliding in, so reading at the peak scored every caption "?" except one, and
    missed a Punish! that reads at distance 0.104 two tenths of a second later.
    Read across the event and keep the closest match per side instead."""
    # Sample the event about every 0.25 s rather than a fixed count: banner
    # events run from a single frame to over three seconds (two captions back to
    # back read as one run), and five frames spread over 3.3 s can straddle the
    # one moment the word is square to the camera.
    t0, t1 = e["t0"], e["last"]
    if t1 <= t0:
        ts = [t0]
    else:
        k = max(n, min(12, int((t1 - t0) / 0.25) + 1))
        ts = [t0 + j * (t1 - t0) / (k - 1) for j in range(k)]
    best, fallback = {}, {}
    for t in ts:
        img = C.frame_at(video, t)
        if img is None:
            continue
        for x0, d, w, margin in rank(img, tpl):
            side = "L" if x0 < 960 else "R"
            r = {"x": x0, "d": round(d, 3), "word": w, "margin": round(margin, 3), "t": round(t, 1), "side": side}
            # A QUALIFYING read beats a merely CLOSER one. Taking the global
            # minimum distance across the event lost segment 3's Punish!: a
            # mid-animation frame matched "Good" at 0.09 with no margin, which
            # then failed the threshold and buried a clean 0.104 Punish! two
            # frames later. Keep the best read that actually passes; fall back
            # to the closest only to report how near it got.
            if d <= MAX_DIST and margin >= MIN_MARGIN:
                if side not in best or d < best[side]["d"]:
                    best[side] = r
            elif side not in fallback or d < fallback[side]["d"]:
                fallback[side] = r
    for side, r in fallback.items():
        if side not in best:
            r["word"] = "?"
            best[side] = r
    return list(best.values())


FULL_FPS = 10.0
FULL_TEAL = 3500     # MIN_TEAL scaled to full resolution (the band is 16x the pixels)


def band_frames(video, a, b, fps=FULL_FPS):
    """(t, band) for every sampled frame of the caption band, FULL resolution.

    ONE ffmpeg process per segment instead of one seek per frame. Seeking into a
    6.7 GB file cost about a quarter second a frame, which made a 25-segment
    sweep an hour of 45-second shell slices. Decoding the band straight through
    is ~1.3 MB a frame and runs many times real time."""
    x, y, w, h = C.BAND
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-ss", "%.3f" % a, "-i", str(video), "-t", "%.3f" % (b - a),
         "-vf", "crop=%d:%d:%d:%d,fps=%s" % (w, h, x, y, fps),
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = w * h * 3
    i = 0
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield a + i / fps, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        i += 1
    p.stdout.close()
    p.wait()


def sweep_segment(video, a, b, tpl):
    """Detect and read in one pass over the segment's caption band.

    caption.banners()/word_bitmap() index a whole 1080p frame, so the band is
    pasted into one reused full-frame buffer rather than re-cropping or
    re-allocating; the rest of the buffer stays black and no caption code looks
    at it."""
    x, y, w, h = C.BAND
    buf = np.zeros((1080, 1920, 3), np.uint8)
    best, fallback, cur, out = {}, {}, None, []

    def close():
        for side, r in fallback.items():
            if side not in best:
                r["word"] = "?"
                best[side] = r
        for r in best.values():
            out.append({**r, "teal": cur["peak"], "span": round(cur["last"] - cur["t0"], 2)})
        best.clear()
        fallback.clear()

    n_ev = 0
    for t, band in band_frames(video, a, b):
        v = int(C.teal(band).sum())
        if v < FULL_TEAL:
            if cur and t - cur["last"] > GAP:
                close()
                cur = None
            continue
        if cur and t - cur["last"] <= GAP:
            cur["last"] = t
            cur["peak"] = max(cur["peak"], v)
        else:
            if cur:
                close()
            cur = {"t0": t, "last": t, "peak": v}
            n_ev += 1
        buf[y:y+h, x:x+w] = band
        for x0, d, wd, margin in rank(buf, tpl):
            side = "L" if x0 < 960 else "R"
            r = {"x": x0, "d": round(d, 3), "word": wd, "margin": round(margin, 3),
                 "t": round(t, 1), "side": side}
            if d <= MAX_DIST and margin >= MIN_MARGIN:
                if side not in best or d < best[side]["d"]:
                    best[side] = r
            elif side not in fallback or d < fallback[side]["d"]:
                fallback[side] = r
    if cur:
        close()
    return out, n_ev


def sweep(video, segs, tpl, verbose=True, checkpoint=None):
    """checkpoint(found) is called after EVERY segment. The shell this runs in on
    Raah's machine kills a job at 45 s, so a sweep that only writes at the end
    loses the whole slice; per-segment writes make a long sweep resumable."""
    found = []
    for i, (a, b) in segs:
        rows, n_ev = sweep_segment(video, a, b, tpl)
        evs = [None] * n_ev
        for r in rows:
            found.append({"seg": i, **r})
        if verbose:
            mine = [f for f in found if f["seg"] == i]
            print("  seg %2d  %6.1f-%6.1fs  %2d banner events  %2d read, %d Punish!"
                  % (i, a, b, len(evs), sum(1 for f in mine if f["word"] != "?"),
                     sum(1 for f in mine if f["word"] == "Punish")), flush=True)
        if checkpoint:
            checkpoint(i, found)
    return found


def write_punishes(video, pun):
    pf = REPLAYS / f"{video}-punishes.json"
    if pf.exists():
        (REPLAYS / f"{video}-punishes.prev.json").write_text(pf.read_text())
    rows = [{"seg": f["seg"], "t": f["t"], "x": f["x"], "d": f.get("d", 0.0),
             "side": f["side"], "margin": f.get("margin"), "from": "find_captions"}
            for f in sorted(pun, key=lambda f: f["t"])]
    pf.write_text(json.dumps(rows, indent=1))
    print("%d Punish! -> %s (previous kept as %s-punishes.prev.json)" % (len(rows), pf.name, video))
    return rows


def main():
    video = sys.argv[1] if len(sys.argv) > 1 else "LongBatch1"
    src = sys.argv[2] if len(sys.argv) > 2 else str(HERE.parent.parent.parent.parent / (video + ".mp4"))
    only = None
    if "--seg" in sys.argv:
        spec = sys.argv[sys.argv.index("--seg") + 1]
        only = ([int(spec)] if "-" not in spec
                else list(range(int(spec.split("-")[0]), int(spec.split("-")[1]) + 1)))
    if "--rewrite" in sys.argv:
        # Rebuild the punish file from a captions file already on disk, without
        # re-reading the video. Useful after a sweep done in slices.
        caps = json.loads((REPLAYS / f"{video}-captions.json").read_text())
        write_punishes(video, [c for c in caps if c["word"] == "Punish"])
        return
    meta = json.loads((REPLAYS / f"{video}-segments.json").read_text())
    segs = list(enumerate(meta["segments"]))
    keep = []
    for i, (a, b) in segs:
        pf = REPLAYS / f"{video}-{i:02d}.json"
        if not pf.exists():
            continue
        if json.loads(pf.read_text()).get("active_seconds", 0) < 15:
            continue
        if only is not None and i not in only:
            continue
        keep.append((i, (a, b)))
    tpl = C.load_templates() if hasattr(C, "load_templates") else {k: v for k, v in np.load(HERE / "caption_words.npz").items()}
    out = REPLAYS / f"{video}-captions.json"
    prev = json.loads(out.read_text()) if out.exists() else []
    done = {i for i, _ in keep}
    prev = [p for p in prev if p["seg"] not in done]

    def checkpoint(i, found):
        out.write_text(json.dumps(sorted(prev + found, key=lambda f: f["t"]), indent=1))

    print(f"{video}: sweeping {len(keep)} segments for captions "
          f"(the file is rewritten after each one, so a killed run keeps what it got)")
    found = sweep(src, keep, tpl, checkpoint=checkpoint)
    found = sorted(prev + found, key=lambda f: f["t"])
    out.write_text(json.dumps(found, indent=1))
    words = {}
    for f in found:
        words[f["word"]] = words.get(f["word"], 0) + 1
    print("\n%d captions: %s" % (len(found), ", ".join("%s ×%d" % kv for kv in sorted(words.items(), key=lambda kv: -kv[1]))))
    pun = [f for f in found if f["word"] == "Punish"]
    _ = write_punishes
    # NEVER write the punish file from a partial sweep. Doing exactly that once
    # replaced a ten-punish ground-truth file with the one punish in segment 1.
    if only is not None:
        print("%d Punish! in this slice — punish file NOT written (partial sweep); "
              "run without --seg to rewrite it" % len(pun))
    elif pun:
        pf = REPLAYS / f"{video}-punishes.json"
        if pf.exists():
            (REPLAYS / f"{video}-punishes.prev.json").write_text(pf.read_text())
        rows = [{"seg": f["seg"], "t": f["t"], "x": f["x"], "d": 0.0, "side": f["side"],
                 "from": "find_captions"} for f in pun]
        pf.write_text(json.dumps(rows, indent=1))
        print("%d Punish! -> %s (previous kept as %s-punishes.prev.json)" % (len(rows), pf.name, video))
    print("-> %s" % out.name)


if __name__ == "__main__":
    main()
