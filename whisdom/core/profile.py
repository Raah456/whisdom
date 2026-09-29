"""Generic habit metrics. Action categories are supplied by the game adapter."""
from collections import Counter

def habit_metrics(match, slot, categories=None):
    categories = categories or {}
    ev=match.inputs(slot)
    if not ev: return None
    minutes = match.duration_frames/match.fps/60.0
    if minutes<=0: return None
    c=Counter(e.action for e in ev)
    m=dict(presses=len(ev), minutes=round(minutes,3), apm=len(ev)/minutes)
    for cat,actions in categories.items():
        n=sum(c[a] for a in actions)
        m[cat]=n; m[cat+"_pm"]=n/minutes
    for a,n in c.items():
        m["n_"+a]=n
    return m
