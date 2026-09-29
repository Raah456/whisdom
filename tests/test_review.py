"""
Properties the death review must hold.

Guards the two degenerate failures found while building it: advice that ignores
game state, and a tendency estimate that counts the wrong windows.

    python3 tests/test_review.py
"""
import os, sys, glob, json, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

from whisdom.agent import review as R

REPLAY = None


def check(name, ok, detail=""):
    print("   %-52s %s%s" % (name, "ok" if ok else "FAIL", "  " + detail if detail else ""))
    return 0 if ok else 1


def run():
    fails = 0
    # --- input classification, no data required ---
    fails += check("recovery move recognised",
                   R.classify_defender({"Heavy", "AimUp", "UpJump"}) == "recovery")
    fails += check("dodge recognised", R.classify_defender({"Dodge", "Right"}) == "airdodge")
    fails += check("bare jump is not a recovery",
                   R.classify_defender({"Jump"}) == "doublejump")
    fails += check("movement alone is not an option", R.classify_defender({"Left"}) is None)
    # a dodge is repositioning, not waiting at the ledge
    fails += check("dodge is not classified as an attack",
                   R.classify_attacker({"Dodge"})[0] == "wait")

    replay = paths.verified_replay(REPLAY)
    if not replay:
        print("   " + paths.missing("verified replay", "WHISDOM_REPLAY"))
        return 1 if fails else 0

    from whisdom.agent.store import Store
    from whisdom.agent.pipeline import ingest_folder
    from whisdom.games.base import get
    ad = get("brawlhalla")
    tmp = tempfile.mkdtemp(prefix="whisdom_review_test_")
    reps = os.path.join(tmp, "r"); os.makedirs(reps); shutil.copy(replay, reps)
    st = Store(os.path.join(tmp, "s"))
    ingest_folder(reps, st, ad.load_match, ad.action_model, ad.categories,
                  pattern=ad.replay_ext)
    doc = None
    for p in glob.glob(os.path.join(st.root, "**", "*.json"), recursive=True):
        try: d = json.load(open(p))
        except Exception: continue
        if isinstance(d, dict) and "match" in d: doc = d; break

    r = R.review_match(doc)
    fails += check("reviews the player who died most", r["player"] == "xugo54")
    fails += check("finds every death", len(r["deaths"]) == 3, "%d" % len(r["deaths"]))
    # tendency must not be dominated by movement inputs
    fails += check("tendency is mostly attacks, not waiting",
                   r["tendency"].get("wait", 0) < 0.5,
                   "wait %.0f%%" % (100 * r["tendency"].get("wait", 0)))
    fails += check("tendency sums to 1", abs(sum(r["tendency"].values()) - 1) < 1e-6)
    fails += check("ambiguity is reported", r["tendency_ambiguous"] > 0)
    # every death must be scored and explained
    fails += check("all deaths scored", all(d["my_ev"] is not None for d in r["deaths"]))
    fails += check("all deaths explained", all(d["why_best"] for d in r["deaths"]))
    # the whole point: the verdict must depend on the situation, not be constant
    gaps = {round(d["gap"], 2) for d in r["deaths"] if d["gap"] is not None}
    fails += check("verdicts differ between deaths", len(gaps) > 1,
                   "gaps %s" % sorted(gaps))

    shutil.rmtree(tmp, ignore_errors=True)
    print("review: %d check(s) failed" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(run())
