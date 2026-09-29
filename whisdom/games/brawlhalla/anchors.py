"""
Anchor-based extraction.

The replay format drifts between patches (the state field grew from 3 to 4 bits
at 8.06, game-settings counts changed repeatedly). Rather than track every
layout, locate known structures by signature and derive the rest relative to
them. Version-proof by construction.
"""
import re
import numpy as np
from whisdom.core.bitstream import BitStream
from .heroes import HEROES
from .inputs import find_blocks, read_block, u32_at_all

NAME_RE = re.compile(r'[A-Za-z0-9 _\-\.]{3,20}$')

def find_names(buf, limit=200000):
    """Length-prefixed ASCII player names -> [(len_pos, name, end_pos)]."""
    s = BitStream(buf); out = []; seen = set()
    for off in range(min(len(buf) * 8 - 200, limit)):
        s.ro = off
        try:
            n = s.u16()
            if not (3 <= n <= 20): continue
            t = bytes(s.bits(8) for _ in range(n)).decode("ascii")
        except Exception:
            continue
        if NAME_RE.match(t) and not t.startswith("Playlist") \
           and any(c.isalpha() for c in t) and t not in seen:
            seen.add(t); out.append((off, t, off + 16 + 8 * n))
    return out

# terminator(1) + tail + state bits, by format generation
_LAST_TAILS = (1+32+4, 1+64+3, 1+64+4)

def last_entity_hero(buf, results_bit):
    """
    Recover the LAST entity's legend by anchoring on the results block.

    The last player has no following name to anchor against, which is what the
    old forward scan tried to work around - and it always returned the same
    wrong offset. But the results block sits a fixed distance downstream:

        ...last PlayerData... | bool(0) | checksum(32) | state(4) | results

    so the entity ends at results_bit - tail and the hero entry is
    (2 + 128*heroCount) before that. Validated against the structural parser on
    the 8.07+ generation: 33/55 recovered, ZERO wrong. It declines rather than
    guesses, which is the property that matters.
    """
    if results_bit is None: return None
    for tail in _LAST_TAILS:
        hs = results_bit - tail - 2 - 128
        if hs < 0: continue
        try:
            s = BitStream(buf, hs); h = s.u32(); s.u32(); stance = s.u32()
        except Exception:
            continue
        if h in HEROES and 0 <= stance <= 3:
            return h
    return None

def heroes_from_anchors(buf, names, results_bit=None):
    """
    Entity N's PlayerData ends 33 bits before entity N+1's name-length field.
    The hero entry sits (2 + 128*heroCount) bits before that. The last entity
    has no following anchor, so scan forward for a plausible entry instead.
    """
    out = []
    for i, (pos, name, end) in enumerate(names):
        hid = None
        if i + 1 < len(names):
            pd_end = names[i + 1][0] - 33
            for hc in (1, 2):
                for x in range(0, 40):
                    hs = pd_end - 2 - 128 * hc - x
                    if hs <= end: continue
                    try:
                        s = BitStream(buf, hs); h = s.u32(); s.u32(); stance = s.u32()
                    except Exception:
                        continue
                    if h in HEROES and 0 <= stance <= 3:
                        hid = h; break
                if hid: break
        else:
            # The LAST entity: anchor on the results block rather than a name.
            # (The old forward scan returned hero 70 for every single file.)
            hid = last_entity_hero(buf, results_bit)
        out.append(dict(name=name, heroId=hid,
                        hero=(HEROES.get(hid) or {}).get("name"),
                        hero_confidence=("anchored" if hid is not None else "unknown")))
    return out

# ---------------------------------------------------------------- results / KOs
def duration_ms(buf):
    d = 0
    for b in find_blocks(buf)[:4]:
        ev = read_block(buf, b["bit"])
        if ev: d = max(d, ev[-1][0])
    return d

def _try_results(buf, off, nplayers=2):
    s = BitStream(buf, off)
    length = s.u32()
    if not s.bit(): return None
    res = {}
    while True:
        try:
            if not s.bit(): break
            eid = s.bits(5); r = s.u16()
        except Exception:
            return None
        if eid == 0 or eid > nplayers + 2: return None
        res[eid] = r
        if len(res) > 6: return None
    if not (1 <= len(res) <= nplayers + 1): return None
    return dict(length=length, results=res, after=s.ro)

def _try_faces(buf, off, dur, nplayers=2):
    """
    Read a faces (KO) block.

    NOTE: the game writes these in DESCENDING timestamp order. Requiring
    ascending order silently rejected every valid block and was the sole reason
    KO extraction "failed" on 9.x/10.x for so long. Accept either direction,
    verify monotonicity, and sort on the way out.
    """
    s = BitStream(buf, off); raw = []
    try:
        while True:
            if not s.bit(): break
            eid = s.bits(5); ts = s.u32()
            if eid == 0 or eid > nplayers + 2: return None
            if ts > dur + 8000 or ts < 500: return None
            raw.append(dict(entityId=eid, ms=ts))
            if len(raw) > 16: return None
    except Exception:
        return None
    if not raw: return None
    ms = [r["ms"] for r in raw]
    ascending  = all(b > a for a, b in zip(ms, ms[1:]))
    descending = all(b < a for a, b in zip(ms, ms[1:]))
    if len(ms) > 1 and not (ascending or descending): return None
    return dict(faces=sorted(raw, key=lambda x: x["ms"]), after=s.ro)

def extract_results_and_kos(buf, nplayers=2, state_bits=4, tol=6000):
    """
    The results block stores match length; the true duration is known from the
    input streams. The correct candidate is the one whose following bits parse
    as a valid results table.
    """
    dur = duration_ms(buf)
    if not dur: return None
    vals = u32_at_all(buf)
    idx = np.nonzero((vals >= max(0, dur - tol)) & (vals <= dur + tol))[0]
    best = None
    for i in idx:
        r = _try_results(buf, int(i), nplayers)
        if not r: continue
        delta = abs(r["length"] - dur)
        if best is None or delta < best[0]:
            best = (delta, int(i), r)
    if not best: return None
    _, off, r = best
    out = dict(length=r["length"], results=r["results"], kos=[], results_bit=off)
    # The KO block position is DERIVABLE, not something to hunt for:
    #   ...last input block... | bool(0) terminator | state(N) | faces
    blocks = find_blocks(buf)
    if blocks:
        end = max(b["end"] for b in blocks)
        for sb in (state_bits, 3):
            probe = end + 1 + sb
            fb = _try_faces(buf, probe, dur, nplayers)
            if fb:
                out["kos"] = fb["faces"]; out["kos_bit"] = probe
                break
        else:
            # fall back to a narrow scan if the derivation misses
            for probe in range(end, min(end + 200, len(buf) * 8 - 64)):
                fb = _try_faces(buf, probe, dur, nplayers)
                if fb and len(fb["faces"]) >= 2:
                    out["kos"] = fb["faces"]; out["kos_bit"] = probe
                    break
    return out
