"""
Data-quality audit.

Regression tests prove behaviour hasn't CHANGED. They cannot prove it was ever
RIGHT - the golden file is generated from the code under test. This audit looks
for internal contradictions instead: places where two independently-derived
facts about the same match should agree, and don't.

That is what caught the hero-identification bug.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import os, sys, json, glob, collections
HERE=os.path.dirname(os.path.abspath(__file__))

class Audit:
    def __init__(self):
        self.findings=collections.defaultdict(list)
        self.counts=collections.Counter()
    def check(self, name, ok, detail=None):
        self.counts[name+"/total"]+=1
        if ok: self.counts[name+"/pass"]+=1
        else:
            self.counts[name+"/fail"]+=1
            if len(self.findings[name])<12 and detail: self.findings[name].append(detail)
    def report(self):
        names=sorted({k.split("/")[0] for k in self.counts})
        print("%-34s %8s %8s %7s"%("CHECK","PASS","FAIL","RATE"))
        print("-"*60)
        bad=0
        for n in names:
            p=self.counts[n+"/pass"]; f=self.counts[n+"/fail"]; t=p+f
            if not t: continue
            if f: bad+=1
            print("%-34s %8d %8d %6.1f%%%s"%(n,p,f,100*p/t," <<<" if f else ""))
        for n in names:
            if self.findings[n]:
                print("\n  %s — examples:"%n)
                for d in self.findings[n][:6]: print("     ",d)
        return bad

def audit_store(store_dir, limit=None, schema_sample=400):
    from whisdom.agent.store import Store
    sys.path.insert(0, os.path.dirname(HERE))
    from whisdom.games.brawlhalla.heroes import HEROES
    st=Store(store_dir); A=Audit()
    files=sorted(glob.glob(os.path.join(store_dir,"matches","*.json")))
    if limit: files=files[:limit]
    seen_ids=set(); content_dupes=collections.Counter()
    validator=None
    try:
        from jsonschema import Draft202012Validator
        schema_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))),"schema","match.schema.json")
        if os.path.exists(schema_path):
            validator=Draft202012Validator(json.load(open(schema_path)))
    except Exception:
        pass
    for i,fp in enumerate(files):
        d=json.load(open(fp))
        m=d["match"]; mid=m["id"]; fps=m["fps"] or 60; dur=m["duration_frames"]
        src=os.path.basename(fp)

        A.check("match_id unique", mid not in seen_ids, "duplicate %s"%mid); seen_ids.add(mid)
        A.check("has players", len(d["players"])>0, src)
        slots=[p["slot"] for p in d["players"]]
        A.check("slots contiguous from 0", slots==list(range(len(slots))), "%s slots=%s"%(src,slots))
        A.check("duration positive", dur>0, "%s dur=%s"%(src,dur))

        # hero ids must exist in the extracted legend table
        for p in d["players"]:
            hid=(p.get("legend") or {}).get("id")
            if hid is not None:
                A.check("hero id in table", hid in HEROES, "%s hero=%s"%(src,hid))

        # inputs: ordered, in range, attributed to a real slot
        ins=d["observations"]["inputs"]
        last=collections.defaultdict(lambda:-1); ordered=True; inrange=True; goodslot=True
        for e in ins:
            if e["slot"] is not None and e["slot"] not in slots: goodslot=False
            if e["frame"]<last[e["slot"]]: ordered=False
            last[e["slot"]]=e["frame"]
            if e["frame"]<0 or e["frame"]>dur+120: inrange=False
        A.check("inputs ordered per slot", ordered, src)
        A.check("inputs within duration", inrange, src)
        A.check("inputs map to a slot", goodslot, src)

        # KOs
        kos=d["observations"]["kos"]
        A.check("kos within duration", all(0<=k["frame"]<=dur+120 for k in kos), src)
        A.check("kos map to a slot", all(k["slot"] in slots for k in kos if k["slot"] is not None), src)

        # results should reference real slots and rank them
        res=m.get("result") or {}
        if res:
            A.check("result keys are slots", all(int(k) in slots for k in res), "%s res=%s"%(src,res))
            A.check("result ranks distinct", len(set(res.values()))==len(res), "%s res=%s"%(src,res))
            # the winner (lowest placement) should not have the most KOs
            if kos and len(res)>1:
                dead=collections.Counter(k["slot"] for k in kos)
                win=min(res,key=lambda k:res[k])
                worst=max(dead,key=lambda s:dead[s]) if dead else None
                A.check("winner isn't the most-KOd", worst is None or int(win)!=worst,
                        "%s winner=%s deaths=%s"%(src,win,dict(dead)))

        # moments
        mo=d["analysis"]["moments"]
        A.check("moment ids unique", len({x["id"] for x in mo})==len(mo), src)
        A.check("moments within duration", all(0<=x["frame"]<=dur+120 for x in mo), src)
        A.check("moment severity 1-5", all(1<=x["severity"]<=5 for x in mo), src)

        # metrics plausibility
        met=d["analysis"].get("metrics") or {}
        for slot,vals in met.items():
            if not vals: continue
            apm=vals.get("apm")
            if apm is not None:
                A.check("apm plausible (0-900)", 0<=apm<=900, "%s apm=%.0f"%(src,apm))
            mins=vals.get("minutes")
            if mins is not None:
                A.check("metric minutes ~ duration", abs(mins*60*fps - dur) < fps*30,
                        "%s minutes=%.2f dur=%.0fs"%(src,mins,dur/fps))

        # provenance honesty
        conf=d["provenance"].get("confidence",{})
        A.check("kos confidence honest",
                (conf.get("kos")=="high")==bool(kos), "%s conf=%s kos=%d"%(src,conf.get("kos"),len(kos)))

        if validator is not None and i<schema_sample:
            errs=list(validator.iter_errors(d))
            A.check("schema valid", not errs, "%s %s"%(src, errs[0].message[:60] if errs else ""))
    return A

if __name__=="__main__":
    store=sys.argv[1] if len(sys.argv)>1 else "/tmp/fl_all"
    lim=int(sys.argv[2]) if len(sys.argv)>2 else None
    A=audit_store(store, lim)
    print()
    bad=A.report()
    print("\n%d check types with failures"%bad)
