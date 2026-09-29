"""
Generic moment detection.

Operates purely on Events plus a game-supplied ActionModel describing how long
actions occupy the player. Nothing here knows what game it is.
"""
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class ActionModel:
    """How long each action blocks re-input, in frames. Supplied by the game adapter."""
    busy_frames: Dict[str,int]
    default_busy: int = 0
    def busy(self, action): return self.busy_frames.get(action, self.default_busy)

def detect_moments(match, model: ActionModel, burst_window=60, burst_count=14, idle_frames=108):
    out=[]
    for p in match.players:
        ev=[e for e in match.inputs(p.slot)]
        last={}
        for e in ev:
            b=model.busy(e.action)
            if b and e.action in last:
                gap=e.frame-last[e.action]
                if gap < b:
                    out.append(dict(frame=e.frame, slot=p.slot, kind="wasted_input", severity=1,
                        title="Wasted %s input"%e.action,
                        detail="%s re-pressed %df in; the previous one occupies %df - the input did nothing"%(e.action,gap,b)))
            last[e.action]=e.frame
        fr=[e.frame for e in ev]
        for i in range(len(fr)):
            j=i
            while j<len(fr) and fr[j]-fr[i]<=burst_window: j+=1
            if j-i>=burst_count:
                out.append(dict(frame=fr[i], slot=p.slot, kind="burst", severity=2,
                    title="Input burst (%d in %.1fs)"%(j-i, burst_window/match.fps),
                    detail="Dense input - typically panic or a dropped sequence."))
        for i in range(1,len(fr)):
            if fr[i]-fr[i-1]>=idle_frames:
                out.append(dict(frame=fr[i-1], slot=p.slot, kind="idle", severity=1,
                    title="Idle %.1fs"%((fr[i]-fr[i-1])/match.fps),
                    detail="No input for %.1f seconds."%((fr[i]-fr[i-1])/match.fps)))
    for k in match.kos():
        out.append(dict(frame=k.frame, slot=k.slot, kind="ko", severity=5,
                        title="KO", detail="Player in slot %s died."%k.slot))
    out.sort(key=lambda m:(-m["severity"], m["frame"]))
    return out

def cluster(moments, window_frames=240):
    out=[]
    for m in sorted(moments,key=lambda x:x["frame"]):
        hit=next((c for c in out if c["kind"]==m["kind"] and c["slot"]==m["slot"]
                  and abs(m["frame"]-c["frame"])<=window_frames), None)
        if hit:
            hit["count"]=hit.get("count",1)+1
            hit["end"]=max(hit.get("end",hit["frame"]), m["frame"])
            hit["severity"]=max(hit["severity"],m["severity"])
        else:
            c=dict(m); c["count"]=1; c["end"]=m["frame"]; out.append(c)
    for c in out:
        if c["count"]>1 and c["kind"]!="ko":
            c["title"]="%s x%d"%(c["title"],c["count"])
            if c["count"]>=4: c["severity"]=min(5,c["severity"]+1)
    out.sort(key=lambda x:(-x["severity"],x["frame"]))
    return out
