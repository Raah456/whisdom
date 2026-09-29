"""
Folder watcher. Polling rather than filesystem events: no extra dependency,
identical behaviour across platforms, and replays appear every few minutes so
a 10-second poll is indistinguishable from instant.
"""
import os, time

def scan(folder, pattern=".replay"):
    out=[]
    for root,_,names in os.walk(folder):
        for n in names:
            if n.endswith(pattern):
                p=os.path.join(root,n)
                try: out.append((p, os.path.getmtime(p), os.path.getsize(p)))
                except OSError: pass
    return out

def watch(folder, on_new, interval=10, settle=2.0, pattern=".replay", stop=None):
    """
    Calls on_new(path) for each file that appears and has stopped growing.
    `settle` guards against reading a replay the game is still writing.
    """
    seen={p:(m,s) for p,m,s in scan(folder,pattern)}
    pending={}
    while True:
        if stop and stop(): return
        now=time.time()
        for p,m,s in scan(folder,pattern):
            if p in seen: continue
            prev=pending.get(p)
            if prev and prev[0]==s and now-prev[1]>=settle:
                on_new(p); seen[p]=(m,s); pending.pop(p,None)
            elif prev is None or prev[0]!=s:
                pending[p]=(s, now)
        time.sleep(interval)
