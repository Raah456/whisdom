"""
Canonical match analysis document (v1.0).

This is the contract between the local agent and everything downstream —
today a local report, tomorrow an HTTP POST body. Designed so the web layer
is additive rather than a rewrite.

Design rules baked in:
  * time is stored in FRAMES (integers, exact). ms is a display concern.
  * every document is tagged with game patch AND analyzer version.
  * players are referenced by stable in-match `slot`; display names are
    treated as aliases, never as identity.
  * every moment carries a stable id so user feedback can attach to it.
  * raw observations and interpretations are kept in separate sections.
"""
import hashlib, json, os, sys
sys.path.insert(0,'/sessions/epic-vigilant-goodall/mnt/outputs/analyzer')

SCHEMA_VERSION  = "1.0"
ANALYZER_VERSION= "0.3.0"
FPS = 60
MS_PER_FRAME = 1000.0/FPS

def frames(ms):
    return int(round(ms / MS_PER_FRAME))

def match_id(path):
    h=hashlib.sha256(open(path,'rb').read()).hexdigest()
    return "bh_"+h[:16]

def moment_id(mid, slot, frame, kind):
    raw="%s|%s|%s|%s"%(mid,slot,frame,kind)
    return "m_"+hashlib.sha1(raw.encode()).hexdigest()[:12]

def build(replay_path, patch=None, video=None):
    from moments import analyse
    from brawlhalla_replay import load, BitStream
    from fast_inputs import find_blocks, read_block, presses
    import re
    res = analyse(replay_path)
    buf = load(replay_path)
    mid = match_id(replay_path)
    base=os.path.basename(replay_path)
    if patch is None:
        m=re.search(r'\[([\d.]+)\]', base); patch = m.group(1) if m else None

    # ---- players (slot-indexed; display name is an alias, not identity) ----
    players=[]
    order=sorted(int(k) for k in res["streams"].keys())
    for i,eid in enumerate(order):
        p = res["players"][i] if i < len(res["players"]) else {}
        players.append(dict(
            slot=i, entity_id=eid,
            display_name=p.get("name"),
            identity_id=None,               # filled later by account linking
            legend=dict(id=p.get("heroId"), name=p.get("hero")),
            team=None, is_bot=None))

    # ---- raw observations ----
    inputs=[]
    for b in find_blocks(buf)[:4]:
        eid=BitStream(buf,b["bit"]-5).bits(5)
        slot=next((pl["slot"] for pl in players if pl["entity_id"]==eid), None)
        for ms,act in presses(read_block(buf,b["bit"])):
            inputs.append(dict(slot=slot, frame=frames(ms), action=act))
    inputs.sort(key=lambda x:(x["frame"], x["slot"] if x["slot"] is not None else 99))
    kos=[]
    for k in res.get("kos",[]):
        slot=next((pl["slot"] for pl in players if pl["entity_id"]==k.get("entityId")), None)
        kos.append(dict(slot=slot, frame=frames(k["ms"])))

    # ---- interpretations ----
    moments=[]
    for m in res["moments"]:
        slot=next((pl["slot"] for pl in players if pl["display_name"]==m.get("who")), None)
        fr=frames(m["ms"])
        moments.append(dict(
            id=moment_id(mid, slot, fr, m["kind"]),
            slot=slot, frame=fr, kind=m["kind"], severity=m["severity"],
            title=m["title"], detail=m["detail"],
            evidence=dict(k for k in m.items() if k[0] in ("leadin","count")) or None,
            feedback=None))          # user can mark agree/disagree later

    doc=dict(
        schema_version=SCHEMA_VERSION,
        analyzer_version=ANALYZER_VERSION,
        match=dict(
            id=mid, source_file=base, game="brawlhalla", patch=patch,
            fps=FPS, duration_frames=frames(res["duration"]),
            playlist=None, online=None, level_id=None, level_name=None,
            has_video=bool(video), video_offset_frames=None),
        players=players,
        observations=dict(inputs=inputs, kos=kos),
        analysis=dict(moments=moments, metrics=None),
        provenance=dict(
            parser="anchor-v1",
            frame_data_patch=patch,
            confidence=dict(
                players="high" if all(p["legend"]["id"] for p in players) else "partial",
                kos="high" if kos else "missing"),
            warnings=[]))
    if not kos:
        doc["provenance"]["warnings"].append("KO extraction unavailable for this patch")
    return doc

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "match.schema.json")

def validate(doc):
    """Validate against the formal JSON Schema (language-neutral contract)."""
    errs=[]
    try:
        import json as _json
        from jsonschema import Draft202012Validator
        sch=_json.load(open(SCHEMA_PATH))
        errs=["%s: %s"%("/".join(str(x) for x in e.path) or "<root>", e.message)
              for e in Draft202012Validator(sch).iter_errors(doc)]
    except ImportError:
        # fall back to structural checks if jsonschema isn't installed
        for k in ("match","players","observations","analysis","provenance"):
            if k not in doc: errs.append("missing section: "+k)
    # cross-field checks the schema can't express
    slots={p["slot"] for p in doc.get("players",[])}
    for i in doc.get("observations",{}).get("inputs",[]):
        if i.get("slot") is not None and i["slot"] not in slots:
            errs.append("input references unknown slot %s"%i["slot"]); break
    return errs

def to_wire(doc):
    """
    Projection that crosses the network: analysis only, no raw observations.
    Full doc with inputs is ~145 KB; this is ~20 KB. See ARCHITECTURE_DECISIONS #9.
    """
    return dict(
        schema_version=doc["schema_version"],
        analyzer_version=doc["analyzer_version"],
        match=doc["match"],
        players=doc["players"],
        observations=dict(inputs=[], kos=doc.get("observations",{}).get("kos",[])),
        analysis=doc["analysis"],
        provenance=doc["provenance"])
