"""
Ground-truth test — the one match verified against a screen recording.

On 2026-08-11 a recording of [10.09] SmallFortressof was checked frame by frame:
stock counters read before and after every KO, and the player confirmed his legend.
That produced the only externally verified facts in this project.

Two parser bugs were found this way, and NO internal check could have caught either:
  * the KO block credits the KILLER, not the victim
  * the stored result field does not mean "lower = better placement"

Both were self-consistent, so the data audit passed at 99.9% while being wrong.
This test exists so they cannot come back.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
from whisdom.games.brawlhalla import load_match

REPLAY = "[10.09] SmallFortressof.replay"

TRUTH = dict(
    players={"xugo54": "DIANA", "NotMashmelIow": "YUMIKO"},
    deaths={"xugo54": [96.4, 148.1, 189.8], "NotMashmelIow": [55.9, 133.2]},
    loser="xugo54",
    duration_s=190,
)

def run(path):
    m = load_match(path)
    names = {p.slot: p.display_name for p in m.players}
    fails = []

    for nm, legend in TRUTH["players"].items():
        got = next((p.character for p in m.players if p.display_name == nm), None)
        if got != legend:
            fails.append("legend for %s: expected %s, got %s" % (nm, legend, got))

    for nm, times in TRUTH["deaths"].items():
        slot = next((s for s, n in names.items() if n == nm), None)
        got = sorted(round(e.frame / m.fps, 1) for e in m.kos() if e.slot == slot)
        if len(got) != len(times) or any(abs(a - b) > 0.5 for a, b in zip(got, times)):
            fails.append("deaths for %s: expected %s, got %s" % (nm, times, got))

    o = m.meta.get("outcome") or {}
    loser = next((names[int(k)] for k, v in o.items() if k != "_deaths" and v == "loss"), None)
    if loser != TRUTH["loser"]:
        fails.append("loser: expected %s, got %s" % (TRUTH["loser"], loser))

    if abs(m.duration_frames / m.fps - TRUTH["duration_s"]) > 2:
        fails.append("duration: expected ~%ss, got %.0fs" % (TRUTH["duration_s"], m.duration_frames / m.fps))

    print("ground truth: %d checks failed" % len(fails))
    for f in fails: print("   FAIL", f)
    if not fails:
        print("   verified: legends, all 5 KO victims and times, loser, duration")
    return 1 if fails else 0

if __name__ == "__main__":
    d = None
    p = paths.verified_replay(sys.argv[1] if len(sys.argv) > 1 else None)
    if not p:
        print(paths.missing("verified replay", "WHISDOM_REPLAY")); sys.exit(0)
    sys.exit(run(p))
