"""
Damage extraction, checked against the replay it was recorded from.

The check needs no hand-made labels. Damage must collapse to white right after a
KO, and KO times come from the replay, so the recording and the replay validate
each other. A pass means all four of these were right at once:

    arc detection · the colour model · reset detection · video/replay alignment

Skips cleanly when the recording or ffmpeg is unavailable.

    python3 tests/test_vision.py [video.mp4] [match.replay]
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

VIDEO = None
REPLAY = None

# Independently verified: legends, death times and loser were confirmed by the
# player and by watching the recording. See tests/test_ground_truth.py.
EXPECT_DEATHS = {"xugo54": 3, "NotMashmelIow": 2}
EXPECT_OFFSET = (-3.0, -1.0)      # seconds; wide enough to allow re-encoding


def run(video=VIDEO, replay=REPLAY):
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("vision test skipped (Pillow not installed)")
        return 0
    from whisdom.vision import video as vid
    if not vid.have_ffmpeg():
        print("vision test skipped (ffmpeg not on PATH)")
        return 0
    video = paths.video(video); replay = paths.verified_replay(replay)
    if not (video and replay):
        print(paths.missing("recording + verified replay", "WHISDOM_VIDEO / WHISDOM_REPLAY"))
        return 0

    from whisdom.agent.store import Store
    from whisdom.agent.pipeline import ingest_folder
    from whisdom.agent import vision_link as vl
    from whisdom.games.base import get

    adapter = get("brawlhalla")
    tmp = tempfile.mkdtemp(prefix="whisdom_vision_test_")
    reps = os.path.join(tmp, "replays")
    os.makedirs(reps)
    import shutil
    shutil.copy(replay, reps)
    store = Store(os.path.join(tmp, "store"))
    ingest_folder(reps, store, adapter.load_match, adapter.action_model,
                  adapter.categories, pattern=adapter.replay_ext)

    doc = None
    import glob, json
    for p in glob.glob(os.path.join(store.root, "**", "*.json"), recursive=True):
        try:
            d = json.load(open(p))
        except Exception:
            continue
        if isinstance(d, dict) and "match" in d:
            doc = d
            break
    if doc is None:
        print("vision: FAIL — replay did not ingest")
        return 1

    names = {p["slot"]: p.get("display_name") for p in doc["players"]}
    res = vl.analyse(doc, video)

    fails = 0
    lo, hi = EXPECT_OFFSET
    if not (lo <= res["offset"] <= hi):
        print("   offset %.2fs outside expected %s  <-- FAIL" % (res["offset"], EXPECT_OFFSET))
        fails += 1
    else:
        print("   offset %+.2fs  (derived, not supplied)" % res["offset"])

    for ai, slot in sorted(res["mapping"].items()):
        who = names.get(slot)
        matched, missed, spurious = res["check"][slot]
        want = EXPECT_DEATHS.get(who)
        ok = want is not None and len(matched) == want and not missed and not spurious
        print("   arc %d -> %-16s %d/%s deaths, %d missed, %d spurious  %s"
              % (ai, who, len(matched), want, len(missed), len(spurious),
                 "" if ok else "<-- FAIL"))
        if not ok:
            fails += 1

    # the attached track must be readable back at match times
    vl.attach(doc, res, video)
    for slot, who in names.items():
        if vl.damage_at(doc, slot, doc["match"]["duration_frames"] / 120.0) is None:
            print("   no damage reading mid-match for %s  <-- FAIL" % who)
            fails += 1

    shutil.rmtree(tmp, ignore_errors=True)
    print("vision: %d check(s) failed" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    v = sys.argv[1] if len(sys.argv) > 1 else VIDEO
    r = sys.argv[2] if len(sys.argv) > 2 else REPLAY
    sys.exit(run(v, r))
