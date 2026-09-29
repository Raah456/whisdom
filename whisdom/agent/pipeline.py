"""
Ingest pipeline: replay file -> schema document -> store.

Deliberately game-neutral: it takes a loader + action model from a game module,
so adding another platform fighter means supplying those two things.
"""
import os, sys, hashlib, json, time
from whisdom.core.detect import detect_moments, cluster
from whisdom.core.profile import habit_metrics

SCHEMA_VERSION="1.1"
ANALYZER_VERSION="0.5.0"

def moment_id(match_id, slot, frame, kind):
    return "m_"+hashlib.sha1(("%s|%s|%s|%s"%(match_id,slot,frame,kind)).encode()).hexdigest()[:12]

def build_document(match, moments, metrics):
    mid=match.match_id
    return dict(
        schema_version=SCHEMA_VERSION,
        analyzer_version=ANALYZER_VERSION,
        match=dict(id=mid, source_file=match.meta.get("source_file"), game=match.game,
                   patch=match.patch, fps=match.fps, duration_frames=match.duration_frames,
                   playlist=match.meta.get("playlist"), online=match.meta.get("online"),
                   level_id=match.meta.get("level_id"), level_name=match.meta.get("level_name"),
                   has_video=False, video_offset_frames=None,
                   outcome=match.meta.get("outcome"),
                   outcome_source=match.meta.get("outcome_source"),
                   death_counts=match.meta.get("death_counts")),
        players=[dict(slot=p.slot, entity_id=None, display_name=p.display_name,
                      identity_id=None,
                      character=dict(id=p.character_id, name=p.character),
                      team=p.team, is_bot=p.is_bot) for p in match.players],
        observations=dict(
            inputs=[dict(slot=e.slot, frame=e.frame, action=e.action) for e in match.inputs()],
            kos=[dict(slot=e.slot, frame=e.frame) for e in match.kos()]),
        analysis=dict(
            moments=[dict(id=moment_id(mid,m.get("slot"),m["frame"],m["kind"]),
                          slot=m.get("slot"), frame=m["frame"], kind=m["kind"],
                          severity=m["severity"], title=m.get("title"), detail=m.get("detail"),
                          evidence=({"count":m["count"]} if m.get("count",1)>1 else None),
                          feedback=None) for m in moments],
            metrics={str(k):v for k,v in metrics.items()}),
        provenance=dict(parser="anchor-v1", frame_data_patch=match.patch,
                        confidence=dict(
                            players="high" if all(p.character_id for p in match.players) else "partial",
                            kos="high" if match.kos() else "missing"),
                        warnings=([] if match.kos() else ["KO extraction unavailable for this patch"])))

def ingest_file(path, store, loader, action_model, categories, force=False):
    """Returns (status, match_id). status in {'ok','skipped','failed'}."""
    try:
        h="bh_"+hashlib.sha256(open(path,'rb').read()).hexdigest()[:16]
        if not force and store.has(h):
            return ("skipped", h)
        match=loader(path)
        # A parse that yields nothing is a FAILURE, not an empty match. Storing
        # empty documents as successes hid a 5% parse-failure rate for days.
        if not match.players or match.duration_frames <= 0 or not match.inputs():
            return ("failed", "%s: parsed to an empty match (%d players, %d frames, %d inputs)"
                    %(os.path.basename(path), len(match.players), match.duration_frames, len(match.inputs())))
        moments=cluster(detect_moments(match, action_model))
        metrics={p.slot: habit_metrics(match, p.slot, categories) for p in match.players}
        doc=build_document(match, moments, metrics)
        store.save(doc, metrics)
        return ("ok", doc["match"]["id"])
    except Exception as e:
        return ("failed", "%s: %s"%(os.path.basename(path), e))

def ingest_folder(folder, store, loader, action_model, categories, pattern=".replay",
                  progress=None, limit=None):
    """`pattern` is the game's replay extension — supplied by the adapter, never assumed."""
    stats=dict(ok=0, skipped=0, failed=0, errors=[])
    files=[]
    for root,_,names in os.walk(folder):
        for n in sorted(names):
            if n.endswith(pattern): files.append(os.path.join(root,n))
    if limit: files=files[:limit]
    for i,f in enumerate(files,1):
        st,info=ingest_file(f, store, loader, action_model, categories)
        stats[st]+=1
        if st=="failed" and len(stats["errors"])<20: stats["errors"].append(info)
        if progress and i%progress==0:
            print("   %d/%d  ok=%d skipped=%d failed=%d"%(i,len(files),stats["ok"],stats["skipped"],stats["failed"]), flush=True)
    stats["total"]=len(files)
    return stats
