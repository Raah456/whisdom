"""
Brawlhalla adapter: .replay -> core.Match

The only module that knows about Brawlhalla's container, bit layouts, hero
tables or input encoding. Everything downstream works on core types.
"""
import os, re, hashlib
from whisdom.core.events import Match, Player, Event
from whisdom.core.detect import ActionModel
from .constants import (INPUT_BITS, FPS, MS_PER_FRAME, DODGE_DURATION,
                        ATTACK_MIN_GAP, CATEGORIES)
from .container import load
from .inputs import find_blocks, read_block, presses, entity_of
from .anchors import find_names, heroes_from_anchors, extract_results_and_kos
from .levels import LEVELS
from .heroes import HEROES
from . import structural

ACTION_MODEL = ActionModel(
    busy_frames={"Dodge": DODGE_DURATION, "Light": ATTACK_MIN_GAP, "Heavy": ATTACK_MIN_GAP},
    default_busy=0)

def _frames(ms): return int(round(ms / MS_PER_FRAME))

def _stage_from_filename(base):
    stem = re.sub(r'^\[[\d.]+\]\s*', '', base).replace('.replay', '')
    stem = re.sub(r'\s*\(\d+\)$', '', stem).strip()
    return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', stem) or None

MAX_MATCH_MS = 30 * 60 * 1000      # no Brawlhalla match runs 30 minutes
MIN_REAL_PRESSES = 20              # a genuine player presses more than this

def _ko_event(frame, killer_slot, n_players):
    """
    Brawlhalla's KO block credits the KILLER, not the victim.

    Verified 2026-08-11 against a screen recording plus the player confirming his
    legend: the times attributed to a slot are the times that player SCORED, not
    the times they died. core.Event uses victim semantics, so normalise here.

    In a 1v1 the victim is unambiguous. With more players it is not recoverable
    from this block, so the victim is left unknown rather than guessed.
    """
    victim = (1 - killer_slot) if n_players == 2 else None
    return Event(frame=frame, slot=victim if victim is not None else killer_slot,
                 action="KO", kind="ko", by=killer_slot)

def _real_blocks(buf):
    """
    Discard false positives from the signature scan.

    Two failure modes to survive:
      * a phantom block with a plausible span (would add a fake player)
      * a phantom block with an ABSURD span - e.g. 14 hours - which, if used as
        the reference for "how long is this match", causes every real block to
        be rejected as too short. Reference off the median of plausible blocks,
        never the maximum.
    """
    blocks = find_blocks(buf)
    if not blocks: return []
    spans = [(b, b.get("last_ts", 0) or 0, b["count"]) for b in blocks[:8]]
    # stage 1: drop the obviously impossible
    plausible = [(b, sp, c) for b, sp, c in spans
                 if 0 < sp <= MAX_MATCH_MS and c >= MIN_REAL_PRESSES]
    if not plausible:
        return [b for b, sp, c in spans if c >= MIN_REAL_PRESSES][:4]
    # stage 2: reference off the median, which a single outlier cannot distort
    ordered = sorted(sp for _, sp, _ in plausible)
    ref = ordered[len(ordered) // 2]
    biggest = max(c for _, _, c in plausible)
    return [b for b, sp, c in plausible if sp >= 0.5 * ref and c >= 0.15 * biggest]

def load_match(path):
    buf = load(path)
    base = os.path.basename(path)
    mid = "bh_" + hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
    pm = re.search(r'\[([\d.]+)\]', base)
    patch = pm.group(1) if pm else None

    order = [(entity_of(buf, b["bit"]), b) for b in _real_blocks(buf)[:4]]
    order.sort(key=lambda x: x[0] if x[0] is not None else 99)
    eids = [e for e, _ in order]

    # Player identification: prefer the STRUCTURAL parse where it succeeds - it
    # reads the hero id straight from the player block and self-validates against
    # the version echo. The anchor method is a heuristic fallback for 9.01+, where
    # the forward walk no longer lands; it mis-identifies players often enough that
    # it must never override a structural result.
    struct = None
    try:
        struct = structural.parse(buf)
    except Exception:
        struct = None
    by_entity = {}
    if struct:
        for e in struct.get("entities", []):
            by_entity[e["id"]] = e
    _rb = None
    try:
        _R = extract_results_and_kos(buf, nplayers=max(2, len(order)))
        _rb = (_R or {}).get("results_bit")
    except Exception:
        _R = None
    pinfo = heroes_from_anchors(buf, find_names(buf), results_bit=_rb) or []

    players, events, dur = [], [], 0
    src = "structural" if struct else "anchor"   # defined even when no blocks are found
    for slot, (eid, b) in enumerate(order):
        se = by_entity.get(eid)
        if se is not None:
            nm, hid = se.get("name"), se.get("heroId")
            src = "structural"
        else:
            info = pinfo[slot] if slot < len(pinfo) else {}
            nm, hid = info.get("name"), info.get("heroId")
            src = "anchor"
        players.append(Player(slot=slot, display_name=nm,
                              character=(HEROES.get(hid) or {}).get("name"),
                              character_id=hid,
                              team=(se or {}).get("team"), is_bot=(se or {}).get("bot")))
        ev = read_block(buf, b["bit"])
        if ev: dur = max(dur, _frames(ev[-1][0]))
        for ms, act in presses(ev):
            events.append(Event(frame=_frames(ms), slot=slot, action=act, kind="input"))

    result = level_id = playlist = online = None
    try:
        R = _R
        if R:
            result = {str(eids.index(k)): v for k, v in (R.get("results") or {}).items() if k in eids}
            for d in R.get("kos") or []:
                if d["entityId"] in eids:
                    events.append(_ko_event(_frames(d["ms"]), eids.index(d["entityId"]), len(eids)))
    except Exception:
        pass
    try:
        S = struct
        if S:
            level_id = S.get("levelId"); playlist = S.get("playlist"); online = S.get("online")
            # structural results are authoritative where the forward walk lands;
            # only fall back to the anchor extraction when they're absent
            sres = S.get("results") or {}
            if sres:
                mapped = {str(eids.index(k)): v for k, v in sres.items() if k in eids}
                if mapped: result = mapped
            if S.get("deaths") and not any(e.kind == "ko" for e in events):
                for d in S["deaths"]:
                    if d["eid"] in eids:
                        events.append(_ko_event(_frames(d["ms"]), eids.index(d["eid"]), len(eids)))
    except Exception:
        pass

    # ---- sanity guards -------------------------------------------------
    # Extraction is heuristic in places; nothing downstream should have to
    # wonder whether a KO at 37 hours or a placement of 2128 is real.
    input_end = max((e.frame for e in events if e.kind == "input"), default=0)
    kept, dropped = [], 0
    for e in events:
        if e.kind == "ko" and not (0 <= e.frame <= input_end + 120):
            dropped += 1; continue
        kept.append(e)
    events = kept
    if result:
        vals = list(result.values())
        # placements are small ranks; some older patches encode 2048/4096
        plausible = all((1 <= v <= 8) or v in (2048, 4096) for v in vals)
        if not plausible or len(set(vals)) != len(vals):
            result = None

    events.sort(key=lambda e: (e.frame, e.slot))

    # ---- outcome, derived from deaths rather than the stored result field ----
    # The result field's encoding is NOT understood: reading "lower = better
    # placement" named the verified LOSER as the winner, and older patches store
    # values like 2048/4096 that are clearly not ranks. Deaths are unambiguous —
    # in a stock match whoever runs out first loses — so derive it instead.
    outcome = None; outcome_source = None; death_counts = None
    kos_ = [e for e in events if e.kind == "ko"]
    if kos_ and len(players) == 2:
        deaths = {p.slot: sum(1 for e in kos_ if e.slot == p.slot) for p in players}
        if len(set(deaths.values())) > 1:
            loser = max(deaths, key=lambda s: deaths[s])
            outcome = {str(p.slot): ("loss" if p.slot == loser else "win") for p in players}
            outcome_source = "deaths"
            death_counts = {str(k): v for k, v in deaths.items()}

    # Fall back to the stored result field where deaths are unavailable.
    # Its encoding was decoded empirically: on 228 matches where a death-derived
    # outcome existed to check against, the winner had the HIGHER value 228/228,
    # across every patch era (older patches use 2048/4096, newer use 1/2).
    # My original reading — lower = better placement — was exactly backwards.
    if outcome is None and result and len(result) >= 2:
        vals = {k: v for k, v in result.items()}
        hi, lo_ = max(vals.values()), min(vals.values())
        if hi != lo_:
            outcome = {k: ("win" if v == hi else "loss") for k, v in vals.items()}
            outcome_source = "result_field"

    name = LEVELS.get(level_id)
    return Match(match_id=mid, game="brawlhalla", patch=patch, fps=FPS,
                 duration_frames=dur, players=players, events=events,
                 meta=dict(source_file=base,
                           result_raw=result,          # encoding NOT understood - do not interpret
                           outcome=outcome,            # per-slot "win"/"loss"
                           outcome_source=outcome_source,   # "deaths" (verified) or "result_field" (decoded)
                           death_counts=death_counts,
                           level_id=level_id,
                           level_name=name or _stage_from_filename(base),
                           level_name_source=("levelId" if name else "filename"),
                           playlist=playlist, online=online,
                           player_source=src, dropped_kos=dropped,
                           has_kos=any(e.kind == "ko" for e in events)))
