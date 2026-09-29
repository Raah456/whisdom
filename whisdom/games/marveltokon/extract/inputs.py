"""What the player actually pressed, and when.

THE GUTTER IS A LOG, AND IT WAS ALREADY BEING READ. `replay_hud.input_rows()` reads
the frame-count column beside the input history every sample; every capture on disk
carries it as `Li` / `Ri`. Nobody had used it.

ROW 0 IS NOT A LOG ROW. The rows sit on a 42 px ladder, but the first group the blob
reader returns is at y=140 while the ladder starts at 232 — a 92 px gap. That row
reads 0% (20 of 20 attempts, both masks tried) while rows 1 onward read 70-100%.
Reading `Li[0]` as the newest input is what made this look like a 13% signal; it is
70%.

THE MODEL, MEASURED. The newest row counts UP while its input is held — the
increment is 6 per 0.1 s sample in 2,629 of 5,402 held samples, which is 1 per game
frame at 59.94 fps. When a new input arrives the counter resets and the old value
slides into row 1. That gives, per input: when it was entered and how long it was
held. Across LongBatch1: 3,969 inputs, median hold 5 frames, the distribution
peaking at 4-6 — what a deliberate press looks like. The counter is two digits, so a
hold of 99 means "99 or more" and is flagged `capped`; 349 of the 3,969 hit it.

WHAT IT IS NOT. This is a COUNT and a DURATION, not an identity. Which direction and
which button remain unread (the rosette reader is disabled at 3/8, and the button
glyphs have not been located). So an input here is "the player entered something and
held it N frames" and nothing more. Say it that way.

WHY IT MATTERS ANYWAY. The opening finder can only say "no NEW attack started", and
it says so — blocking, dashing and repeating a move all read the same to it. Input
activity inside a window separates "did nothing" from "did something the panel does
not count", which is the single biggest open question the app has.
"""
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPLAYS = HERE.parent / "data" / "replays"

CAP = 99            # the gutter's counter is two digits: 99 means "99 or more"
MAX_STEP = 6        # frames the counter may advance between 0.1 s samples
SLOP = 6            # tolerance matching the old head against row 1 after a scroll


def inputs(rec, side):
    """[{t, held, t_end}] — every input entered on this side, in order."""
    key = {"L": "Li", "R": "Ri"}[side]
    out, prev, started = [], None, None
    for s in rec["samples"]:
        if s.get("frozen"):
            continue
        cur = s.get(key)
        if not cur or len(cur) < 3:
            continue
        cur = cur[1:]                     # row 0 is not a log row
        t = s["t"]
        if prev is not None and prev[0] is not None and cur[0] is not None:
            if cur[0] > prev[0]:
                pass                      # still held
            elif cur[1] is not None and abs(cur[1] - prev[0]) <= SLOP:
                out.append({"t": round(started if started is not None else t, 2),
                            "held": int(prev[0]), "capped": int(prev[0]) >= CAP,
                            "t_end": round(t, 2)})
                started = t
        if started is None:
            started = t
        prev = cur
    return out


def by_capture(video):
    out = {}
    for f in sorted(REPLAYS.glob(f"{video}-[0-9][0-9].json")):
        r = json.loads(f.read_text())
        out[r["segment"]] = {side: inputs(r, side) for side in ("L", "R")}
    return out


def during(rows, a, b):
    """Inputs entered inside [a, b]."""
    return [x for x in rows if a <= x["t"] <= b]


def main():
    import statistics
    video = sys.argv[1] if len(sys.argv) > 1 else "LongBatch1"
    data = by_capture(video)
    n = sum(len(v[s]) for v in data.values() for s in ("L", "R"))
    held = [x["held"] for v in data.values() for s in ("L", "R") for x in v[s]]
    out = REPLAYS / f"{video}-inputs.json"
    out.write_text(json.dumps({k: v for k, v in data.items()}, indent=1))
    print("%s: %d inputs across %d segments" % (video, n, len(data)))
    if held:
        print("  hold: median %d frames, p90 %d, longest %d"
              % (statistics.median(held), sorted(held)[int(len(held) * .9)], max(held)))
        c = collections.Counter(min(h, 15) for h in held)
        print("  " + ", ".join("%s%df×%d" % ("" if k < 15 else "≥", k, v) for k, v in sorted(c.items())))
    print("-> %s" % out.name)


if __name__ == "__main__":
    main()
