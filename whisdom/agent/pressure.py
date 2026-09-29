"""
Pressure analysis: what changes in the seconds before a player dies?

Uses only KO timings + input streams + frame data, so it needs no state
reconstruction. The key measure is not how OFTEN an action is used but whether
its QUALITY degrades - specifically, inputs the game provably discards.
"""
import json, glob, os, collections, statistics as st, math

WINDOW_FRAMES = 300      # 5 seconds at 60fps

def _committed_presses(seq, action, duration):
    """
    Presses of a committed action, flagged when the game must have discarded them
    (pressed while the previous one was still resolving). Which action this is,
    and how long it lasts, comes from the game adapter.
    """
    out=[]; last=None
    for f,a in seq:
        if a != action: continue
        out.append((f, last is not None and (f-last) < duration))
        last=f
    return out

def _mean(x): return sum(x)/len(x) if x else 0.0

def _cohens_d(a,b):
    if not a or not b: return 0.0
    s=math.sqrt((st.pvariance(a)+st.pvariance(b))/2) or 1e-9
    return (_mean(a)-_mean(b))/s

def analyse(store_dir, player, adapter, window=WINDOW_FRAMES):
    cfg = adapter.pressure
    if cfg is None:
        raise SystemExit("%s does not define a pressure action" % adapter.display_name)
    counts={"death":collections.defaultdict(list), "kill":collections.defaultdict(list)}
    waste={"death":[0,0], "kill":[0,0]}
    waste_per_event={"death":[], "kill":[]}
    n={"death":0,"kill":0}; matches=0
    for fp in glob.glob(os.path.join(store_dir,"matches","*.json")):
        d=json.load(open(fp))
        me=[p["slot"] for p in d["players"] if p.get("display_name")==player]
        if not me: continue
        me=me[0]
        kos=d["observations"]["kos"]
        if not kos: continue
        ins=[(e["frame"],e["action"]) for e in d["observations"]["inputs"] if e["slot"]==me]
        if not ins: continue
        matches+=1
        dp=_committed_presses(ins, cfg.action, cfg.duration_frames)
        for k in kos:
            end=k["frame"]; key="death" if k["slot"]==me else "kill"
            n[key]+=1
            c=collections.Counter(a for f,a in ins if end-window<=f<=end)
            for a in cfg.tracked_actions:
                counts[key][a].append(c.get(a,0))
            counts[key]["TOTAL"].append(sum(c.values()))
            win=[(f,w) for f,w in dp if end-window<=f<=end]
            if win:
                w=sum(1 for _,x in win if x)
                waste[key][0]+=w; waste[key][1]+=len(win)
                waste_per_event[key].append(w/len(win))
    out=dict(player=player, game=adapter.name, action=cfg.action, action_label=cfg.label,
             matches=matches, deaths=n["death"], kills=n["kill"],
             window_seconds=window/adapter.fps, actions={}, quality={})
    for a in counts["death"]:
        dv,kv=_mean(counts["death"][a]),_mean(counts["kill"][a])
        out["actions"][a]=dict(before_death=round(dv,2), before_kill=round(kv,2),
                               pct_diff=round(((dv-kv)/kv*100) if kv else 0),
                               effect=round(_cohens_d(counts["death"][a],counts["kill"][a]),2))
    for k in ("death","kill"):
        w,t=waste[k]
        out["quality"][k]=dict(wasted=w, total=t,
                                     rate=round(100*w/t,1) if t else None,
                                     per_event_mean=round(100*_mean(waste_per_event[k]),1))
    out["quality"]["effect"]=round(_cohens_d(waste_per_event["death"],waste_per_event["kill"]),2)
    return out

def summarise(r):
    L=[]
    L.append("Pressure analysis — %s"%r["player"])
    L.append("%d matches with KO data · %d deaths · %d kills · %.0fs window"
             %(r["matches"],r["deaths"],r["kills"],r["window_seconds"]))
    dq=r["quality"]
    L.append("")
    L.append("%s QUALITY (inputs the game provably discards)" % r["action_label"].upper())
    L.append("   before a death : %.1f%% wasted (%d of %d)"%(dq["death"]["rate"],dq["death"]["wasted"],dq["death"]["total"]))
    L.append("   before a kill  : %.1f%% wasted (%d of %d)"%(dq["kill"]["rate"],dq["kill"]["wasted"],dq["kill"]["total"]))
    L.append("   effect size    : d=%+.2f"%dq["effect"])
    L.append("")
    L.append("ACTION RATES (mean presses in the window)")
    L.append("   %-13s %-13s %-12s %-8s %s"%("action","before death","before kill","diff","effect"))
    for a,v in sorted(r["actions"].items(), key=lambda x:-abs(x[1]["effect"])):
        if v["before_death"]==0 and v["before_kill"]==0: continue
        L.append("   %-13s %-13.2f %-12.2f %+6.0f%%  d=%+.2f%s"%(
            a,v["before_death"],v["before_kill"],v["pct_diff"],v["effect"],
            "  <<<" if abs(v["effect"])>=0.2 else ""))
    return "\n".join(L)
