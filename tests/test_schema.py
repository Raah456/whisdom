"""Every document the pipeline emits must validate against the formal schema."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sys, os, glob, json
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths
SCHEMA=paths.schema()

def run(replay_root, n=12):
    from whisdom.games.brawlhalla import load_match, ACTION_MODEL, CATEGORIES
    from whisdom.core.detect import detect_moments, cluster
    from whisdom.core.profile import habit_metrics
    from whisdom.agent.pipeline import build_document
    try:
        from jsonschema import Draft202012Validator
        v=Draft202012Validator(json.load(open(SCHEMA)))
    except Exception as e:
        print("schema test skipped (%s)"%e); return 0
    files=sorted(glob.glob(os.path.join(replay_root,"**","*.replay"),recursive=True))[:n]
    bad=0
    for f in files:
        m=load_match(f)
        doc=build_document(m, cluster(detect_moments(m, ACTION_MODEL)),
                           {p.slot: habit_metrics(m,p.slot,CATEGORIES) for p in m.players})
        errs=list(v.iter_errors(doc))
        if errs:
            bad+=1
            print("   INVALID %-30s %s"%(os.path.basename(f)[:30], errs[0].message[:80]))
    print("schema: %d/%d documents valid"%(len(files)-bad,len(files)))
    return 0 if bad==0 else 1

if __name__=="__main__":
    root=paths.replays(sys.argv[1] if len(sys.argv)>1 else None)
    if not root:
        print(paths.missing("replay folder","WHISDOM_REPLAYS")); sys.exit(0)
    sys.exit(run(root))
