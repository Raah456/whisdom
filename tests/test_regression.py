"""
Regression suite.

The Brawlhalla parser was reverse-engineered by inference across 45 patch
versions. There is no specification to check against, so the guard is a golden
snapshot: a stratified sample of replays whose parsed output is known-good.

Any refactor that changes these outputs is a bug until proven otherwise.

    python tests/test_regression.py [replay_root]
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths
import sys, os, json, glob, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
from whisdom.games.brawlhalla import load_match

GOLDEN = os.path.join(HERE, "golden_parse.json")

def signature(match):
    return dict(
        match_id=match.match_id, patch=match.patch, dur=match.duration_frames,
        players=[[p.slot, p.display_name, p.character, p.character_id] for p in match.players],
        n_inputs=len(match.inputs()), n_kos=len(match.kos()),
        result=match.meta.get("result"), level=match.meta.get("level_name"),
        input_hash=hashlib.sha1(
            str([(e.frame, e.slot, e.action) for e in match.inputs()]).encode()).hexdigest()[:16])

def run(replay_root):
    golden = json.load(open(GOLDEN))
    index = {os.path.basename(f): f for f in
             glob.glob(os.path.join(replay_root, "**", "*.replay"), recursive=True)}
    same = diff = err = missing = 0
    failures = []
    for name, expected in golden.items():
        path = index.get(name)
        if not path:
            missing += 1; continue
        try:
            got = signature(load_match(path))
        except Exception as e:
            err += 1; failures.append((name, "raised %s" % e)); continue
        exp = dict(expected); exp["players"] = [list(x) for x in exp.get("players", [])]
        if json.dumps(got, sort_keys=True) == json.dumps(exp, sort_keys=True):
            same += 1
        else:
            diff += 1
            for k in got:
                if json.dumps(got[k], sort_keys=True) != json.dumps(exp.get(k), sort_keys=True):
                    failures.append((name, "%s: expected %r got %r" % (k, exp.get(k), got[k])))
                    break
    print("regression: %d identical, %d differing, %d errored, %d not found"
          % (same, diff, err, missing))
    for n, f in failures[:15]:
        print("   FAIL %-34s %s" % (n[:34], f))
    return 0 if (diff == 0 and err == 0 and same > 0) else 1

if __name__ == "__main__":
    root = paths.replays(sys.argv[1] if len(sys.argv) > 1 else None)
    if not root:
        print(paths.missing("replay folder", "WHISDOM_REPLAYS")); sys.exit(0)
    sys.exit(run(root))
