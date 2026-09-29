"""
Review the exchanges that killed you, and say what was worth more.

This is where everything meets: inputs from the replay (frame-accurate), damage
from the video, tendencies from the corpus, payoffs from frame data. It answers
the question the project set out to answer — not "you dodge a lot", but "at this
moment, at this damage, against this opponent, dodging was worth less than the
alternative, and here is the number".

WHAT IS INFERRED, AND HOW CONFIDENTLY
-------------------------------------
There is no position data, so nothing here claims to know you were offstage. What
it does know is that you died, and which buttons both players pressed in the
seconds before. The option each press represents is inferred from co-occurring
inputs, which the replay records exactly:

    AimUp + UpJump + Heavy   -> recovery move   (unambiguous; also implies offstage)
    Dodge                    -> air dodge       (unambiguous)
    Jump / UpJump alone      -> double jump     (unambiguous)
    Heavy + AimDown          -> down heavy      (down air or ground pound - the
                                                 two cannot be told apart without
                                                 knowing whether you were airborne)
    Light / Heavy otherwise  -> contest
    nothing                  -> no input

The defender mapping is solid. The ATTACKER mapping is coarser — "ground pound"
and "go deep" both read as Heavy+AimDown — so attacker options are reported with
that ambiguity stated rather than hidden.
"""
from collections import Counter

from whisdom.core.options import expected_values
from whisdom.games.brawlhalla import payoffs as P
from whisdom.agent import vision_link as vl

PAIR_FRAMES = 6          # inputs this close together are one action
DEFAULT_WINDOW = 3.0     # seconds before a death that count as "the exchange"


def _grouped(inputs, slot, lo, hi):
    """Inputs for one player in a frame range, grouped into simultaneous presses."""
    xs = [i for i in inputs if i["slot"] == slot and lo <= i["frame"] <= hi]
    xs.sort(key=lambda i: i["frame"])
    groups, cur = [], []
    for i in xs:
        if cur and i["frame"] - cur[0]["frame"] > PAIR_FRAMES:
            groups.append(cur); cur = []
        cur.append(i)
    if cur:
        groups.append(cur)
    return [(g[0]["frame"], {x["action"] for x in g}) for g in groups]


def classify_defender(acts):
    """Which defensive option a group of simultaneous inputs represents."""
    if "Heavy" in acts and ("AimUp" in acts or "UpJump" in acts):
        return "recovery"
    if "Dodge" in acts:
        return "airdodge"
    if "Light" in acts or "Heavy" in acts:
        return "contest"
    if "Jump" in acts or "UpJump" in acts:
        return "doublejump"
    return None


def classify_attacker(acts):
    """
    Which edgeguard option a group represents. Coarser than the defender side.
    Returns (key, ambiguous).
    """
    if "Heavy" in acts and "AimDown" in acts:
        return "deep_dair", True      # or ground pound; cannot separate
    if "Light" in acts or "Heavy" in acts:
        return "ledge_sair", True
    if "Dodge" in acts or "Jump" in acts or "UpJump" in acts:
        return "wait", False          # repositioning, not committing
    return None, False


def defender_choice(doc, slot, ko_frame, window=DEFAULT_WINDOW):
    """The last committed defensive option before a death, and when."""
    fps = doc["match"].get("fps") or 60
    lo = ko_frame - int(window * fps)
    best = None
    for frame, acts in _grouped(doc["observations"]["inputs"], slot, lo, ko_frame):
        k = classify_defender(acts)
        if k:
            best = (k, frame, sorted(acts))
    return best


def tendency(doc, slot, windows, window=DEFAULT_WINDOW):
    """
    Distribution over the opponent's edgeguard options, from what they pressed
    while actually killing this player.

    Two things this deliberately does NOT do, because an earlier version did and
    the result was degenerate:

      * it only looks at windows where the player being reviewed DIED, so the
        opponent was genuinely attacking. Including their own deaths mixed in
        situations where they were the one recovering.
      * it does not count a dodge or a jump as "waiting at the ledge". Those are
        repositioning. "Wait" is measured as the share of exchanges containing NO
        attack at all, which is what waiting actually looks like in the inputs.

    Returns (dist, sample_size, ambiguous_share).
    """
    fps = doc["match"].get("fps") or 60
    c = Counter()
    ambiguous = 0
    waits = 0
    for ko_frame in windows:
        lo = ko_frame - int(window * fps)
        attacked = False
        for _f, acts in _grouped(doc["observations"]["inputs"], slot, lo, ko_frame):
            if not ("Light" in acts or "Heavy" in acts):
                continue          # movement, not a committed edgeguard option
            k, amb = classify_attacker(acts)
            if k:
                c[k] += 1
                attacked = True
                ambiguous += 1 if amb else 0
        if not attacked:
            waits += 1
    n = sum(c.values()) + waits
    if not n:
        return {}, 0, 0.0
    dist = {k: v / n for k, v in c.items()}
    if waits:
        dist["wait"] = waits / n
    return dist, n, (ambiguous / n if n else 0.0)


def review_death(doc, slot, ko_frame, opp_tendency, window=DEFAULT_WINDOW):
    """
    Compare what the player did against every alternative, at the damage they
    were actually at. Returns a dict, or None when there is nothing to compare.
    """
    fps = doc["match"].get("fps") or 60
    seconds = ko_frame / float(fps)
    players = {p["slot"]: p for p in doc["players"]}
    opp_slot = next((s for s in players if s != slot), None)

    chose = defender_choice(doc, slot, ko_frame, window)
    if not chose or not opp_tendency:
        return None
    key, frame, acts = chose

    my_dmg = vl.damage_at(doc, slot, frame / float(fps))
    their_dmg = vl.damage_at(doc, opp_slot, frame / float(fps)) if opp_slot is not None else None

    # weapon is not in the replay; the engine needs one, so this is stated openly
    ctx = dict(defender_weapon="Sword", attacker_weapon="Sword",
               defender_damage=my_dmg, attacker_damage=their_dmg)
    rows = P.model().matrix(ctx)
    ranked = expected_values(rows, opp_tendency)

    label = {k: lbl for k, lbl in P.DEF_OPTIONS}[key]
    mine = next((r for r in ranked if r[0] == label), None)
    best = ranked[0]
    row = next(r for r in rows if r["key"] == key)

    return dict(
        seconds=seconds, at=frame / float(fps), slot=slot,
        chose=label, chose_key=key, inputs=acts,
        my_damage=my_dmg, their_damage=their_dmg,
        my_ev=(mine[1] if mine else None), best=best[0], best_ev=best[1],
        gap=(best[1] - mine[1]) if mine else None,
        confidence=row.get("confidence", 1.0),
        ranked=[(o, v) for o, v, _r in ranked],
        why_best=_why(rows, best[0], opp_tendency),
    )


def _why(rows, option_label, tend):
    """The reason for the highest-weighted attacker option."""
    row = next((r for r in rows if r["option"] == option_label), None)
    if not row or not tend:
        return ""
    top = max(tend, key=tend.get)
    cell = row["cells"].get(top)
    return cell["why"] if cell else ""


def review_match(doc, name=None, window=DEFAULT_WINDOW):
    """Review every death of one player (default: whoever died most)."""
    players = {p["slot"]: p for p in doc["players"]}
    kos = {}
    for m in doc.get("analysis", {}).get("moments", []):
        if m.get("kind") == "ko" and m.get("slot") is not None:
            kos.setdefault(m["slot"], []).append(m["frame"])
    if not kos:
        return None
    if name:
        slot = next((s for s, p in players.items()
                     if (p.get("display_name") or "").lower() == name.lower()), None)
        if slot is None:
            return None
    else:
        slot = max(kos, key=lambda s: len(kos[s]))
    opp = next((s for s in players if s != slot), None)

    # only the windows where THIS player died: those are the exchanges where the
    # opponent was the one attacking
    tend, n, amb = tendency(doc, opp, sorted(kos.get(slot, [])), window)
    out = [review_death(doc, slot, f, tend, window) for f in sorted(kos.get(slot, []))]
    return dict(slot=slot, player=players[slot].get("display_name"),
                opponent=players[opp].get("display_name") if opp is not None else None,
                tendency=tend, tendency_n=n, tendency_ambiguous=amb,
                deaths=[d for d in out if d])
