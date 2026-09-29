"""
Version-adaptive structural parser.

Works on 6.06-9.00 where the forward walk still lands. Parameters are DERIVED
per file (state-field width and game-settings count both changed across patches)
rather than hardcoded per version.

Known drift:
    6.06-7.10  state 3 bits, 10 settings, version echo + checksum
    8.00-8.05  state 3 bits, 12 settings, version echo + checksum
    8.06       state 4 bits, 16 settings, version echo + checksum
    8.07-9.00  state 4 bits, 15 settings, checksum only
    9.01+      player block gained fields; forward walk fails (use anchors.py)
"""
import re
from whisdom.core.bitstream import BitStream
from .anchors import find_names
from .heroes import HEROES

def detect_params(buf):
    """Derive (state_bits, settings_count) from the first player-name anchor."""
    names = find_names(buf, limit=140000)
    if not names: return None
    o1 = names[0][0]
    for sb in (4, 3):
        s = BitStream(buf)
        try:
            s.bits(sb); s.u32(); s.u32(); pid = s.u32()
            if pid != 0:
                n = s.u16()
                if not (5 <= n <= 80): continue
                t = bytes(s.bits(8) for _ in range(n)).decode("ascii", "replace")
                if not t.startswith("Playlist"): continue
            s.bit()
            rem = o1 - 33 - 16 - 32 - sb - s.ro
            if rem >= 0 and rem % 32 == 0:
                return sb, rem // 32
        except Exception:
            continue
    return None

def parse(buf):
    p = detect_params(buf)
    if not p: return None
    SB, GS = p
    for tail in (64, 32):          # version echo + checksum, or checksum only
        try:
            s = BitStream(buf)
            s.bits(SB); s.u32(); ver = s.u32(); pid = s.u32()
            playlist = s.string() if pid != 0 else None
            online = s.bit(); s.bits(SB)
            [s.u32() for _ in range(GS)]
            level_id = s.u32(); hc = s.u16()
            if not (0 < hc < 8): raise ValueError("heroCount")
            ents = []
            while s.bit():
                eid = s.u32(); nm = s.string()
                colour = s.u32(); s.u32(); s.u32(); s.u32()
                [s.u32() for _ in range(8)]; s.u16(); s.u16()
                while s.bit(): s.u32()
                s.u16(); team = s.u32(); s.u32()
                heroes = [(s.u32(), s.u32(), s.u32(), s.u32()) for _ in range(hc)]
                bot = s.bit(); hand = s.bit()
                if hand: s.u32(); s.u32(); s.u32()
                ents.append(dict(id=eid, name=nm, team=team, colour=colour, bot=bot,
                                 heroId=heroes[0][0] if heroes else None))
                if len(ents) > 6: raise ValueError("entities")
            if not ents or not all(e["heroId"] in HEROES for e in ents):
                raise ValueError("hero ids")
            s.ro += tail
            st = s.bits(SB)
            out = dict(version=ver, playlist=playlist, online=online, levelId=level_id,
                       entities=ents, deaths=[], results={}, length=None)
            stop = False; guard = 0
            while not stop and guard < 12:
                guard += 1
                if st == 6:
                    out["length"] = s.u32()
                    if tail == 64: s.u32()
                    if s.bit():
                        while s.bit(): out["results"][s.bits(5)] = s.u16()
                    s.u32()
                elif st in (5, 7):
                    a = []
                    while s.bit(): a.append(dict(eid=s.bits(5), ms=s.u32()))
                    if st == 5: out["deaths"] = sorted(a, key=lambda x: x["ms"])
                elif st == 1:
                    while s.bit():
                        s.bits(5); cnt = s.u32()
                        for _ in range(cnt):
                            s.u32()
                            if s.bit(): s.bits(14)
                elif st == 2:
                    stop = True
                else:
                    break
                if s.nbits - s.ro < 8: break
                if not stop: st = s.bits(SB)
            if out["length"] and 5000 < out["length"] < 2000000:
                return out
        except Exception:
            continue
    return None
