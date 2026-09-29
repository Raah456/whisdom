"""Free time you did not use.

The north star is "after losing, tell me what I could have done to win". The
first honestly answerable version of that is not "you missed a punish" — it is
**you had N frames in which your opponent could not act, and you threw nothing.**

WHY NOT "MISSED PUNISH". A punish means the opponent's move was BLOCKED and
recovered late. Telling block from hit from knockdown is not possible with the
fields the overlay gives us, and getting it wrong is not a rounding error: the
first window inspected by eye was a 25-hit combo ending in a knockdown, where
the "victim" was at -44 because the other player had just comboed them into the
floor. Reporting that as a missed punish would be worse than reporting nothing.

WHAT `Recovery` ACTUALLY IS. Measured across the corpus: **237 of 264
multi-sample windows ramp monotonically at exactly -6 per 0.1 s sample, which on
59.94 fps footage is -1 per game frame.** It is a STOPWATCH, not a settled
number — it counts frames while one player is free and the other is stuck, then
snaps to 0. It is also zero-sum (left == -right in 99.8% of 9,334 samples), so a
negative reading on one side means that side is the stuck one.

So the terminal magnitude of a window is a MEASUREMENT: how many frames of
freedom the other player actually had. That is better than a frame-data
prediction, because it is what happened rather than what should have.

WHAT "DID NOTHING" MEANS, PRECISELY. The panel only describes attacks, so a new
move is detected as a change in `Attack Startup`. This means:
  - repeating the SAME move reads as no new move (under-reports use — safe),
  - dashing, jumping or blocking read as "nothing" (over-reports waste).
So an opening reported here means **threw no new attack**, not "stood still".
Say it that way in any output a human reads - and do not say it as a fault. Of
the 69 findings Raah graded, 17 were windows where he was deliberately blocking
or baiting. "N frames free, no new attack" is the measurement; whether it was a
mistake is his to say, not this file's.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPLAYS = HERE.parent / "data" / "replays"

STUCK = -6          # below this, one side is meaningfully unable to act
MIN_FRAMES = 12     # a window worth talking about; ~0.2 s
GRACE = 0.3         # seconds either side, for sampling slop
MAX_GAP = 5         # unread samples that may sit inside one window (0.5 s)


def live(rec):
    return [s for s in rec["samples"] if not s.get("frozen")]


def windows(rec, side):
    """Maximal runs where `side` is stuck. `side` is the DISADVANTAGED one.

    An UNREAD sample does not end a run. This is the third place in this
    pipeline where treating null as evidence caused a real error: here it
    shattered one 1.8-second knockdown into six separate "openings" of 44-49
    frames each, which then dominated the top of the ranking — the same finding
    counted six times. Null means unknown; only a reading that is actually >
    STUCK ends the run.

    A run is still closed if the gap of unread samples is long, because at some
    point "unknown" stops being a plausible continuation.
    """
    out, cur, gap = [], None, 0
    for s in live(rec):
        v = s[side]["Recovery"]
        if v is None:
            gap += 1
            if cur and gap > MAX_GAP:
                out.append(cur)
                cur = None
            continue
        gap = 0
        if v <= STUCK:
            cur = cur or {"start": s["t"], "worst": v}
            cur["end"], cur["worst"] = s["t"], min(cur["worst"], v)
        elif cur:
            out.append(cur)
            cur = None
    if cur:
        out.append(cur)
    return out


def acted(rec, side, a, b):
    """Did `side` start a new attack in this span?"""
    return any(a - GRACE <= m["t"] <= b + GRACE for m in rec["moves"][side])


def openings(rec, min_frames=MIN_FRAMES):
    """Windows where one player was free and threw nothing."""
    out = []
    for stuck, free in (("L", "R"), ("R", "L")):
        for w in windows(rec, stuck):
            frames = -w["worst"]
            if frames < min_frames:
                continue
            if acted(rec, free, w["end"] - frames / 59.94, w["end"]):
                continue
            # The measurement is `frames` - the terminal value of the stopwatch.
            # `w["start"]` is only "when the reader first saw it": if the first
            # samples of a ramp were unread, it lands late, which is why a
            # 44-frame window could appear to span 0.2 s. Anchor on the END and
            # derive the start, so the numbers cannot disagree with each other.
            out.append({"segment": rec["segment"], "free": free, "stuck": stuck,
                        "end": round(w["end"], 2),
                        "start": round(w["end"] - frames / 59.94, 2),
                        "first_seen": w["start"], "frames": frames})
    return out


# --------------------------------------------------------------- clustering ---
# One stall, one whiff or one knockdown does not produce one window: the reader
# loses samples, the stopwatch restarts, and the same moment lands as several
# findings. Segment 13 of LongBatch1 produced SEVEN findings inside seven
# seconds (2227.9 - 2234.2), and the largest of them ranked first in the whole
# capture. Raah graded all seven separately and called the later ones lag.
#
# So windows on the same side of the same segment, within MERGE_GAP of each
# other, are ONE event. The event keeps the frame count of its largest member -
# the stopwatch measures the whole moment, so the largest reading is the
# measurement and the others are re-reads of it, not additional free time.
#
# The id is the largest member's, so grades already given survive the change;
# `members` carries the rest so the app can find takes left on any of them.
MERGE_GAP = 1.5     # seconds between windows that still count as one moment


def merge(ops, gap=MERGE_GAP):
    """Windows -> events. Same segment, same free side, within `gap` = one event."""
    events = []
    for o in sorted(ops, key=lambda o: (o["segment"], o["free"], o["start"])):
        last = events[-1] if events else None
        if (last and last["segment"] == o["segment"] and last["free"] == o["free"]
                and o["start"] - last["end"] <= gap):
            last["members"].append(o)
            last["end"] = max(last["end"], o["end"])
            last["start"] = min(last["start"], o["start"])
            continue
        events.append({**o, "members": [o]})
    out = []
    for e in events:
        big = max(e["members"], key=lambda m: m["frames"])
        out.append({**big,
                    "start": round(e["start"], 2), "end": round(e["end"], 2),
                    "anchor": big["end"],
                    "windows": len(e["members"]),
                    "members": [round(m["end"], 2) for m in e["members"]],
                    "span": round(e["end"] - e["start"], 2)})
    out.sort(key=lambda o: -o["frames"])
    return out


def load(video="LongBatch1", min_live=15.0):
    recs = []
    for f in sorted(REPLAYS.glob(f"{video}-[0-9]*.json")):
        r = json.loads(f.read_text())
        if r["active_seconds"] >= min_live:
            recs.append(r)
    return recs


def main():
    video = sys.argv[1] if len(sys.argv) > 1 else "LongBatch1"
    recs = load(video)
    found = [o for r in recs for o in openings(r)]
    found.sort(key=lambda o: -o["frames"])
    live_s = sum(r["active_seconds"] for r in recs)
    total = sum(o["frames"] for o in found)
    print(f"{len(recs)} segments, {live_s/60:.1f} min live")
    print(f"{len(found)} openings, {total:,} frames unused "
          f"({total/59.94:.1f} s, {total/59.94/live_s*100:.1f}% of live time)\n")
    print(" seg  side   time        frames")
    for o in found[:25]:
        print(f"  {o['segment']:2d}   {o['free']}    {o['start']:8.1f}s   {o['frames']:4d}")
    out = REPLAYS / f"{video}-openings.json"
    out.write_text(json.dumps(found, indent=1))
    ev = merge(found)
    out2 = REPLAYS / f"{video}-events.json"
    out2.write_text(json.dumps(ev, indent=1))
    multi = [e for e in ev if e["windows"] > 1]
    print(f"\n{len(found)} windows -> {len(ev)} events ({len(multi)} merged, "
          f"biggest cluster {max([e['windows'] for e in ev], default=0)})")
    print(f"-> {out.name}, {out2.name}")


if __name__ == "__main__":
    main()


# --------------------------------------- okizeme vs punish: NOT SOLVED YET ---
# Six openings inspected by eye split two ways: some are the opponent committed
# to a move and whiffing (a real missed punish), and some are the opponent
# KNOCKED DOWN after a combo. Both are literally "free frames you did not use",
# but they are different mistakes and only one is a punish.
#
# TWO DISCRIMINATORS WERE TRIED AND BOTH FAILED. Recorded so they are not
# retried:
#
# 1. Recent damage. If the free player had just landed a combo, the disadvantage
#    should be a knockdown. Tested against the six hand-labelled cases:
#    Damage / Combo / Highest Combo did not change in ANY of them, within 1 s or
#    2 s. The panel holds last-move values rather than updating promptly, so
#    these fields carry no timing information at this resolution.
#
# 2. The teal "Knockdown" caption. It is trivially detectable - 26% of the crop
#    when present, 0.0% when not, four orders of magnitude apart. But as a
#    classifier over a 3-second lookback it agreed with the hand labels on only
#    2 of 6. The caption fires at the instant of a knockdown, and the relationship
#    between that instant and a later opening is evidently not a fixed offset.
#
# AND THE TEST IS ALSO SUSPECT. The six labels were read off small filmstrip
# tiles - the same mistake that sank the direction reader (T-014), where the
# expectation, not the reader, turned out to be the problem. Before a third
# attempt: get ground truth that does not depend on squinting at a contact sheet.
#
# A better route exists and is untried: THE GAME LABELS PUNISHES ITSELF. An
# orange "Punish!" caption appears on screen, as does "Counter!". Those are the
# game's own judgement, in the same fixed-position, high-contrast style as
# everything else here. Read them, and a punish stops being inferred at all.
#
# knockdown_flash() is kept because it works as a DETECTOR; it is the
# *classifier* built on it that did not. Do not label openings with it.
#
# --------------------------------- lag / rollback: TWO MORE FAILED ATTEMPTS ---
# Raah graded 69 findings on 2026-08-25 and tagged nine of them `lag` - "both
# characters look idle and the frame counter stutters". Those tags are ground
# truth, so two panel-based discriminators were tested against them and BOTH
# FAILED. Recorded so they are not retried:
#
# 1. Per-window stopwatch stutter. `Recovery` ramps -6 per 0.1 s sample, so a
#    rollback stall should freeze it. Median ramp rate is 6.0 on lag-tagged
#    windows AND 6.0 on real-tagged ones; median stalled-step share 0.22 vs
#    0.18. No separation. The extreme cases (rate 0, >80% stalled steps) do pick
#    out two lag windows - but they also pick out open:14:2277.5, which Raah
#    called real. Two of nine is not a classifier.
#
# 2. Per-segment health. Lag is a property of a connection, so the whole segment
#    should look sick. Median stall share is 28.1% on the five segments carrying
#    lag tags vs 22.7% on the fourteen without - real, but far too small: the
#    two WORST segments in the capture (0 at 37.8%, 18 at 36.1%) carry no lag
#    tags at all.
#
# CONCLUSION: what Raah sees is not in the panel. It is in the picture - both
# fighters idle while the world keeps running. The untried route is the game's
# own match clock in the HUD (top centre, high contrast, fixed position, same
# style as everything else read here): during a rollback stall it should stop or
# stutter while the reader's own wall clock does not. That is a video read, not
# a panel read, and it has not been attempted.
#
# UNTIL THEN, NO CLASSIFIER SHIPS. The app carries Raah's own `lag` tags forward
# to the other windows in the same segment, labelled as HIS judgement, and says
# nothing of its own.
KD_BAND = (0, 660, 1920, 110)      # x, y, w, h - full width; the caption mirrors
KD_LOOKBACK = 3.0                  # seconds before the opening to search
KD_FRACTION = 0.03                 # 0.26 when present, 0.000 when not


def knockdown_before(video, t, lookback=KD_LOOKBACK, fps=10.0):
    """Did a Knockdown caption flash in the `lookback` seconds before `t`?"""
    import subprocess
    import numpy as np
    import cv2
    x, y, w, h = KD_BAND
    a = max(t - lookback, 0.0)
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{t:.3f}", "-i", video,
         "-vf", f"fps={fps},crop={w}:{h}:{x}:{y}", "-f", "rawvideo",
         "-pix_fmt", "bgr24", "-"], capture_output=True)
    n = w * h * 3
    for i in range(len(p.stdout) // n):
        img = np.frombuffer(p.stdout[i*n:(i+1)*n], np.uint8).reshape(h, w, 3)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        teal = ((hsv[..., 0] > 82) & (hsv[..., 0] < 100) &
                (hsv[..., 1] > 110) & (hsv[..., 2] > 110))
        if teal.mean() >= KD_FRACTION:
            return True
    return False


# classify() removed: see the note above. Openings are reported unlabelled
# until there is a discriminator that survives a real test.
