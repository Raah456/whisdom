"""Every combo in a capture, cut out of the panel exactly — and what the punishes were worth.

THE FIELD. The frame-data panel shows, per side, `Damage` and `Combo`. Read across a
capture they are: **Damage = the damage of the last hit that landed. Combo = the running
damage total of the combo in progress.** Both LINGER at their last value after the combo
ends; neither returns to 0 on its own.

THE CUT, AND WHY IT IS NOT A HEURISTIC. A combo's first hit is the one sample where the
running total equals the last hit — `Combo == Damage`. A later hit cannot tie: if the
total before it were X and the hit did D, the new total is X+D, which equals D only when
X is 0. So `Combo == Damage`, on a sample where the value actually CHANGED, is an exact
combo boundary. (On a lingering plateau the equality still holds, which is why the change
test is required — without it a one-hit combo restarts on every sample and the count came
out 3,994 instead of 190.) A DROP also opens a combo, covering the case where two hits
land inside one 0.1 s sample and the first-hit equality is never sampled.

THE CHECK. If that reading is right, every increment inside a combo must equal that
sample's `Damage`. Measured across LongBatch1: **702 of 756 increments match exactly
(92.9%)**, and every mismatch is an integer multiple of the shown Damage (400 = 2x200,
3000 = 2x1500, 6000 = 2x3000) — two hits inside one 0.1 s sample. So the totals are right
and the hit COUNT is a lower bound. Say it that way.

PUNISHES. `<video>-punishes.json` holds the moments the game itself printed "Punish!",
with the side it printed on. Joined to the combos above, the caption lands 0.2-1.7 s
AFTER the first hit of a combo on that side in all 10 of LongBatch1's captions - the
caption follows the hit, it does not precede it. That consistency is the join's receipt.

WHAT IT IS FOR. "The game gave you a free hit; what did you do with it." A punish that
stops at one hit is the cheapest damage in the game left on the floor. It is a
measurement, not a verdict: a one-hit punish can be a correct choice (no meter, wrong
range, the opponent's assist was out). Report the number and let the player say.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPLAYS = HERE.parent / "data" / "replays"

PUNISH_LAG = 2.5    # seconds a "Punish!" caption may trail the hit it is about

# A REVERTED RULE, RECORDED SO IT IS NOT RETRIED. "The comboing side cannot be
# the stuck side" looked airtight - Recovery is a zero-sum stopwatch, negative on
# whoever cannot act - and it fixed Vid1 segment 2, where R's counter sat at
# 5,500 for 2.3 s while Recovery ran R negative. But LongBatch1 segment 20 kills
# it: R lands 8,000 at 2801.0, sits at Recovery -40 for a second, and then the
# game's OWN counter continues that same combo 8,000 -> 14,400 -> 31,055. The
# panel is the authority on what one combo is, and it says that is one combo. So
# Recovery negative on the attacking side means their move is in recovery, not
# that the combo ended, and the rule is wrong. The Vid1 case is handled instead
# by joining the caption to the HIT it follows rather than to a combo's first
# hit - a punish can land on a later hit of a counter that has not reset.


def combos(rec, side):
    """The Combo field -> individual combos. See the module docstring for the rule.

    A null reading is UNKNOWN, not zero: hold the previous value rather than closing the
    combo (the same mistake shattered openings into six in find_openings.py)."""
    out, cur, prev = [], None, None
    for s in rec["samples"]:
        if s.get("frozen"):
            continue
        v, dm, t = s[side].get("Combo"), s[side].get("Damage"), s["t"]
        if v is None:
            continue
        if v == 0:
            if cur:
                out.append(cur)
                cur = None
            prev = 0
            continue
        if v != prev:
            first_hit = dm is not None and v == dm
            dropped = prev is not None and prev > 0 and v < prev
            if first_hit or dropped:
                if cur:
                    out.append(cur)
                cur = {"segment": rec["segment"], "side": side, "t0": round(t, 2),
                       "t1": round(t, 2), "damage": v, "hits": 1, "steps": [(round(t, 2), v)],
                       "hits_are": "a lower bound - two hits can land inside one 0.1s sample"}
            elif cur and prev is not None and v > prev:
                cur["damage"] = v
                cur["t1"] = round(t, 2)
                cur["hits"] += 1
                cur["steps"].append((round(t, 2), v))
            elif not cur and prev is not None and v > prev:
                # No combo open and the counter moved: this is a combo whose first
                # hit was never sampled cleanly (Damage unread on that frame, so the
                # Combo == Damage marker was missed). Open here rather than drop the
                # whole combo - Vid1 segment 2 lost a 6-hit, 18,300 combo this way.
                cur = {"segment": rec["segment"], "side": side, "t0": round(t, 2),
                       "t1": round(t, 2), "damage": v, "hits": 1, "steps": [(round(t, 2), v)],
                       "first_hit_inferred": True,
                       "hits_are": "a lower bound - two hits can land inside one 0.1s sample"}
        prev = v
    if cur:
        out.append(cur)
    for c in out:
        c["span"] = round(c["t1"] - c["t0"], 2)
        c["character"] = (rec.get("characters") or {}).get(side) or "?"
    return out


def verify(recs):
    """The check in the docstring, run again on whatever capture this is."""
    ok = bad = 0
    aliased = 0
    for r in recs:
        for side in ("L", "R"):
            prev = None
            for s in r["samples"]:
                if s.get("frozen"):
                    continue
                v, dm = s[side].get("Combo"), s[side].get("Damage")
                if v is None:
                    continue
                if prev is not None and v > prev and dm:
                    if v == dm:
                        pass
                    elif v - prev == dm:
                        ok += 1
                    else:
                        bad += 1
                        if (v - prev) % dm == 0:
                            aliased += 1
                prev = v
    return {"increments_matching_damage": ok, "not_matching": bad,
            "of_those_an_exact_multiple": aliased,
            "share_ok": round(ok / max(1, ok + bad), 3)}


def hits_of(rec, side):
    """(t, damage_total_after_this_hit, index_within_its_combo, combo) for every hit."""
    out = []
    for c in combos(rec, side):
        for k, (t, tot) in enumerate(c["steps"], 1):
            out.append({"t": t, "total": tot, "index": k, "combo": c})
    return out


def join_punishes(video, all_combos, by_seg=None):
    """Each "Punish!" caption -> the HIT it followed, and that hit's combo.

    NOT the combo's first hit. In LongBatch1 every one of the 15 captions does
    follow a first hit, 0.3-1.6 s behind it, which is where the rule came from.
    Vid1 segment 2 is the exception that generalised it: the caption at 189.3 s
    trails the second hit of a combo whose counter had not reset since 3.7 s
    earlier. A punish is a hit on a recovering opponent; usually that starts the
    combo, but the counter does not have to agree."""
    p = REPLAYS / f"{video}-punishes.json"
    if not p.exists():
        return []
    hits = []
    for c in all_combos:
        for k, st in enumerate(c.get("steps") or [], 1):
            hits.append({"t": st[0], "total": st[1], "index": k, "c": c})
    out = []
    for cap in json.loads(p.read_text()):
        cand = [h for h in hits
                if h["c"]["segment"] == cap["seg"] and h["c"]["side"] == cap["side"]
                and cap["t"] - PUNISH_LAG <= h["t"] <= cap["t"]]
        h = max(cand, key=lambda h: h["t"]) if cand else None
        c = h["c"] if h else None
        row = {"seg": cap["seg"], "side": cap["side"], "caption_t": cap["t"],
               "damage": c and c["damage"], "hits": c and c["hits"],
               "t0": c and c["t0"], "span": c and c["span"],
               "character": c and c["character"],
               "hit_index": h and h["index"],
               "caption_lag": h and round(cap["t"] - h["t"], 2)}
        if h:
            before = 0 if h["index"] == 1 else c["steps"][h["index"] - 2][1]
            row["from_punish_on"] = c["damage"] - before
            row["receipt"] = ("Punish! at %.1fs; the hit it follows landed %.1fs earlier%s, "
                              "and that combo reached %s damage over %d reading%s"
                              % (cap["t"], row["caption_lag"],
                                 "" if h["index"] == 1 else " (hit %d of the combo — the counter had not reset)" % h["index"],
                                 "{:,}".format(c["damage"]), c["hits"], "" if c["hits"] == 1 else "s"))
        else:
            row["from_punish_on"] = None
            row["receipt"] = ("Punish! at %.1fs; no hit landed on that side in the %.1fs before it — "
                              "the moment it belongs to is outside the read window"
                              % (cap["t"], PUNISH_LAG))
        out.append(row)
    return out


def load(video="LongBatch1", min_live=15.0):
    recs = []
    for f in sorted(REPLAYS.glob(f"{video}-[0-9]*.json")):
        r = json.loads(f.read_text())
        if r["active_seconds"] >= min_live:
            recs.append(r)
    return recs


def main():
    import statistics as st
    video = sys.argv[1] if len(sys.argv) > 1 else "LongBatch1"
    recs = load(video)
    cs = [c for r in recs for side in ("L", "R") for c in combos(r, side)]
    cs.sort(key=lambda c: (c["segment"], c["t0"]))
    v = verify(recs)
    pun = join_punishes(video, cs)
    print(f"{len(recs)} segments -> {len(cs)} combos")
    if cs:
        d = sorted(c["damage"] for c in cs)
        h = sorted(c["hits"] for c in cs)
        one = sum(1 for c in cs if c["hits"] <= 1)
        print(f"  damage  median {st.median(d):,.0f}   p90 {d[int(len(d)*.9)]:,}   max {d[-1]:,}")
        print(f"  hits    median {st.median(h):.0f}   max {h[-1]}   ended after one hit: {one} ({one/len(cs)*100:.0f}%)")
    print(f"  check   {v['increments_matching_damage']} of {v['increments_matching_damage']+v['not_matching']} "
          f"increments equal the shown Damage ({v['share_ok']*100:.1f}%); "
          f"{v['of_those_an_exact_multiple']} of the rest are an exact multiple (two hits in one sample)")
    if pun:
        got = [p for p in pun if p["damage"]]
        print(f"\n{len(pun)} Punish! captions, {len(got)} joined to a combo")
        print("  seg  caption      damage   hits  lag")
        for p in pun:
            print("  %3d  %8.1fs  %8s  %4s  %4s" % (
                p["seg"], p["caption_t"], "{:,}".format(p["damage"]) if p["damage"] else "-",
                p["hits"] or "-", ("%.1f" % p["caption_lag"]) if p["caption_lag"] is not None else "-"))
        if got:
            pd = sorted(p["damage"] for p in got)
            one = sum(1 for p in got if p["hits"] <= 1)
            print(f"  punish damage median {st.median(pd):,.0f}; {one} of {len(got)} stopped at one hit")
    out = REPLAYS / f"{video}-combos.json"
    out.write_text(json.dumps({"video": video, "combos": cs, "punishes": pun, "check": v}, indent=1))
    print(f"\n-> {out.name}")


if __name__ == "__main__":
    main()
