"""
Damage extraction from a recording's HUD.

Replays store inputs only — no damage, no positions. But the HUD shows each
player's damage as a coloured arc beside their portrait, and that arc is readable.

WHAT THE ARC ACTUALLY DOES (verified frame-by-frame, 2026-08-11)
---------------------------------------------------------------
The arc is a FIXED-SIZE crescent. It does not grow or fill. Only its COLOUR
changes, along a single ramp:

    white  ->  pale yellow  ->  yellow  ->  orange  ->  red      then white again on death

So damage is a pure colour reading. An earlier version of this module also used
"how much of the arc is drawn" as a signal; that was wrong — the apparent fill
change was the portrait's blue background passing a saturation filter, and blue
hue (~215 deg) wrapped around to read as MAXIMUM damage. Any damage figure
produced before this rewrite should be discarded.

This gives a monotonic 0..1 estimate, not an exact percentage — enough to answer
"was he fresh or nearly dead when he made that choice", which is the context the
option engine needs.

SELF-VALIDATING
---------------
Damage must return to white immediately after a KO, and KO times are known exactly
from the replay. `validate()` checks the arcs against those times, so the extractor
is verified against independent ground truth rather than trusted.
"""
import colorsys
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

@dataclass
class ArcRegion:
    """
    Where a player's damage arc sits (pixels, in the source resolution).

    `mask` marks which pixels inside the box are actually arc, sampled on a
    `mask_w` x `mask_h` grid. Masking matters: the box unavoidably contains
    portrait art and the stock numeral, and orange hair reads exactly like an
    orange arc if you average the whole box.
    """
    x: int
    y: int
    w: int
    h: int
    mask_w: int = 0
    mask_h: int = 0
    mask: list = field(default_factory=list, repr=False)

    def crop(self, image):
        return image.crop((self.x, self.y, self.x + self.w, self.y + self.h))


@dataclass
class DamageReading:
    seconds: float
    hue: float | None      # signed degrees; +60 yellow (low) -> 0 red (high)
    sat: float             # 0..1; near zero means a white (fresh) arc
    estimate: float        # 0..1 monotonic damage estimate
    fresh: bool            # True when the arc is white — player just spawned


# ---------------------------------------------------------------------------
# Colour model
# ---------------------------------------------------------------------------

_WARM_LO, _WARM_HI = 335.0, 70.0     # the arc's colour band, wrapping through red
_FRESH_SAT = 0.22                     # below this the arc is white


def _signed_hue(h):
    """Map hue to a continuous scale through red: yellow +60 ... red 0 ... deep red negative."""
    return h - 360.0 if h > 180.0 else h


def _is_arc_colour(h, s, v):
    return s > 0.40 and v > 0.45 and (h <= _WARM_HI or h >= _WARM_LO)


def damage_from(hue, sat):
    """
    Position on the white -> yellow -> orange -> red ramp, as 0..1.

    Saturation carries the low end (white to pale yellow, where hue is unstable);
    hue carries the top end (yellow through orange to red).
    """
    if hue is None or sat < _FRESH_SAT:
        return 0.0
    sat_c = min(1.0, sat / 0.85)
    hue_c = max(0.0, min(1.0, (60.0 - hue) / 60.0))
    return max(0.0, min(1.0, 0.35 * sat_c + 0.65 * hue_c))


def read_arc(image, region=None):
    """
    Read one arc. `image` is either a full frame (with `region`) or a crop already
    matching the region's box. Returns (signed_hue | None, saturation, value).
    """
    im = image.convert("RGB")
    if region is not None and (im.width, im.height) != (region.w, region.h):
        im = region.crop(im)
    if region is not None and region.mask:
        im = im.resize((region.mask_w, region.mask_h))
        px = [p for p, keep in zip(im.getdata(), region.mask) if keep]
    else:
        px = list(im.getdata())
    hs, ss, vs = [], [], []
    for r, g, b in px:
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        h *= 360.0
        # keep arc-coloured pixels, plus white ones (a fresh arc is white)
        if _is_arc_colour(h, s, v):
            hs.append(_signed_hue(h)); ss.append(s); vs.append(v)
        elif s < _FRESH_SAT and v > 0.70:
            ss.append(s); vs.append(v)
    if not ss:
        return None, 0.0, 0.0
    med = lambda xs: sorted(xs)[len(xs) // 2]
    return (med(hs) if hs else None), med(ss), med(vs)


def series(frames, region=None):
    """
    frames : iterable of (seconds, PIL.Image)
    Returns [DamageReading].

    No normalisation against the rest of the match — the colour ramp is absolute,
    so a player who never climbs above 40% reads as never climbing above 40%.
    """
    out = []
    for t, im in frames:
        h, s, _v = read_arc(im, region)
        est = damage_from(h, s)
        out.append(DamageReading(seconds=t, hue=h, sat=s, estimate=est,
                                 fresh=est < 0.12))
    return out


# ---------------------------------------------------------------------------
# Deaths
# ---------------------------------------------------------------------------

def resets(readings, drop=0.30, floor=0.18, window=2.5, min_gap=6.0):
    """
    Times where damage collapses — i.e. the player just died and respawned.

    Detected as a large DROP to near-white rather than a threshold crossing, so it
    survives a death from moderate damage (a KO off the top at 60% resets just as
    hard as one at 200%).
    """
    out = []
    last = -1e9
    for i, a in enumerate(readings):
        for b in readings[i + 1:]:
            if b.seconds - a.seconds > window:
                break
            if a.estimate - b.estimate >= drop and b.estimate <= floor:
                if b.seconds - last > min_gap:
                    out.append(b.seconds)
                    last = b.seconds
                break
    return out


def validate(readings, ko_seconds, tolerance=6.0):
    """
    Check the extractor against known KO times: every death should be followed by
    a reset to white. Returns (matched, missed, spurious).
    """
    found = resets(readings)
    matched = [k for k in ko_seconds if any(abs(f - k) <= tolerance for f in found)]
    missed = [k for k in ko_seconds if k not in matched]
    spurious = [f for f in found if not any(abs(f - k) <= tolerance for k in ko_seconds)]
    return matched, missed, spurious


# ---------------------------------------------------------------------------
# Arc auto-detection
# ---------------------------------------------------------------------------
# Hand-positioned crops are fragile — they break on any resolution, HUD scale or
# window layout. These find the arcs from the footage itself.
#
# Two signals separate a damage arc from everything else on screen:
#   1. It CHANGES over the match (high temporal variance), unlike static HUD art.
#   2. It goes WARM, unlike the timer and stock numerals, which are always white.
# Characters are warm and move, but only briefly at any one pixel; requiring a
# pixel to be warm across a good fraction of sampled frames rejects them.
#
# Final confirmation is structural: arcs come in PAIRS — same size, same row.
# That constraint is what makes detection position-independent, so the HUD can
# sit anywhere on screen (this footage has it top-right, not bottom-centre).

def _hsv_planes(im, scale):
    """Downscale; return (size, warm_mask, grey) as flat sequences."""
    im = im.convert("RGB")
    if scale != 1:
        im = im.resize((max(1, im.width // scale), max(1, im.height // scale)))
    try:
        import numpy as np
    except ImportError:
        warm, grey = [], []
        for r, g, b in im.getdata():
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            warm.append(_is_arc_colour(h * 360, s, v))
            grey.append((r + g + b) / 3)
        return im.size, warm, grey
    a = np.asarray(im, dtype=np.float32) / 255.0
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    v = a.max(-1); mn = a.min(-1); c = v - mn
    s = np.where(v > 0, c / np.maximum(v, 1e-6), 0.0)
    h = np.zeros_like(v)
    nz = c > 1e-6
    rm, gm, bm = (v == r) & nz, (v == g) & nz, (v == b) & nz
    h[rm] = ((g - b)[rm] / c[rm]) % 6
    h[gm] = ((b - r)[gm] / c[gm]) + 2
    h[bm] = ((r - g)[bm] / c[bm]) + 4
    h *= 60.0
    warm = (s > 0.40) & (v > 0.45) & ((h <= _WARM_HI) | (h >= _WARM_LO))
    return im.size, warm.ravel(), (a.mean(-1) * 255).ravel()


def _components(mask, w, h, min_area):
    """4-connected components over a flat boolean mask -> [(x0,y0,x1,y1,area,[idx])]."""
    seen = bytearray(w * h)
    out = []
    for start in range(w * h):
        if not mask[start] or seen[start]:
            continue
        stack = [start]; seen[start] = 1; idx = []
        x0 = x1 = start % w; y0 = y1 = start // w
        while stack:
            i = stack.pop(); idx.append(i)
            x, y = i % w, i // w
            if x < x0: x0 = x
            if x > x1: x1 = x
            if y < y0: y0 = y
            if y > y1: y1 = y
            for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if 0 <= nx < w and 0 <= ny < h:
                    j = ny * w + nx
                    if mask[j] and not seen[j]:
                        seen[j] = 1; stack.append(j)
        if len(idx) >= min_area:
            out.append((x0, y0, x1, y1, len(idx), idx))
    return out


def _best_pair(cands, tol_y, tol_size):
    """Pick the two components that best look like a pair of arcs."""
    best = None
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            a, b = cands[i], cands[j]
            ay, by = (a[1] + a[3]) / 2, (b[1] + b[3]) / 2
            aw, bw = a[2] - a[0], b[2] - b[0]
            ah, bh = a[3] - a[1], b[3] - b[1]
            if abs(ay - by) > tol_y:
                continue
            if max(aw, bw) and abs(aw - bw) / max(aw, bw) > tol_size:
                continue
            if max(ah, bh) and abs(ah - bh) / max(ah, bh) > tol_size:
                continue
            score = a[4] + b[4] - abs(ay - by) * 10
            if best is None or score > best[0]:
                best = (score, sorted([a, b], key=lambda c: c[0]))
    return best[1] if best else None


def find_arcs(frames, scale=4, warm_frac=0.25, var_frac=0.18, pad=0.12):
    """
    Locate the damage arcs from frames sampled across a match.

    frames : list of PIL.Image spread over the match (12+ recommended, so damage
             actually varies between them)
    returns: [ArcRegion] ordered left-to-right with masks filled in, or None

    Coordinates are in the source resolution of the frames supplied.
    """
    if len(frames) < 4:
        raise ValueError("need at least 4 sampled frames")
    size, warm0, grey0 = _hsv_planes(frames[0], scale)
    w, h = size
    n = len(frames)
    warm_count = [1 if warm0[i] else 0 for i in range(w * h)]
    sums = list(grey0)
    sqs = [g * g for g in grey0]
    for f in frames[1:]:
        _, wm, gr = _hsv_planes(f, scale)
        for i in range(w * h):
            if wm[i]:
                warm_count[i] += 1
            g = gr[i]; sums[i] += g; sqs[i] += g * g
    var = [max(0.0, sqs[i] / n - (sums[i] / n) ** 2) ** 0.5 for i in range(w * h)]
    vmax = max(var) or 1.0
    mask = [(var[i] > var_frac * vmax) and (warm_count[i] >= warm_frac * n)
            for i in range(w * h)]
    cands = _components(mask, w, h, min_area=max(12, (w * h) // 20000))
    if len(cands) < 2:
        return None
    cands.sort(key=lambda c: -c[4])
    pair = _best_pair(cands[:12], tol_y=max(4, h // 40), tol_size=0.55)
    if not pair:
        return None
    out = []
    for x0, y0, x1, y1, _area, idx in pair:
        bw, bh = (x1 - x0 + 1), (y1 - y0 + 1)
        px, py = int(bw * pad) + 1, int(bh * pad) + 1
        rx0, ry0 = max(0, x0 - px), max(0, y0 - py)
        rw, rh = bw + 2 * px, bh + 2 * py
        member = set(idx)
        m = [((ry0 + yy) * w + (rx0 + xx)) in member
             for yy in range(rh) for xx in range(rw)]
        out.append(ArcRegion(x=rx0 * scale, y=ry0 * scale, w=rw * scale, h=rh * scale,
                             mask_w=rw, mask_h=rh, mask=m))
    return out


def align(arc_series, kos_by_slot, max_offset=120.0, step=0.5, tolerance=4.0):
    """
    Work out, from the death pattern alone, (a) the time offset between the
    recording and the replay and (b) which HUD arc belongs to which player.

    The recording and the replay are independent observations of the same match,
    so nothing needs to be labelled by hand: each player's deaths form a distinct
    fingerprint in time, and only one alignment fits.

    arc_series  : [[DamageReading]] per detected arc, left-to-right
    kos_by_slot : {slot: [death_seconds]} from the replay
    returns     : (score, offset, {arc_index: slot}) or None

    `offset` satisfies:  video_seconds = match_seconds + offset
    """
    import itertools
    if not arc_series or not kos_by_slot:
        return None
    found = [resets(s) for s in arc_series]
    slots = list(kos_by_slot)
    if len(slots) > len(found):
        return None
    best = None
    steps = int(max_offset / step)
    for perm in itertools.permutations(range(len(found)), len(slots)):
        for k in range(-steps, steps + 1):
            off = k * step
            score = 0.0
            resid = []
            for ai, slot in zip(perm, slots):
                want = [t + off for t in kos_by_slot[slot]]
                for wv in want:
                    near = [f for f in found[ai] if abs(f - wv) <= tolerance]
                    if near:
                        score += 1
                        resid.append(min(near, key=lambda f: abs(f - wv)) - wv)
                score -= 0.5 * sum(1 for f in found[ai]
                                   if not any(abs(f - wv) <= tolerance for wv in want))
            # Tolerance is deliberately loose, so many offsets tie on score alone.
            # Break ties on fit quality, otherwise the winner is whichever offset
            # the loop happened to reach first — which can be seconds out.
            fit = -(sum(abs(r) for r in resid) / len(resid)) if resid else -tolerance
            key = (score, fit)
            if best is None or key > (best[0], best[3]):
                mapping = {ai: slot for ai, slot in zip(perm, slots)}
                # Recentre the offset on the matched deaths themselves.
                shift = (sorted(resid)[len(resid) // 2] if resid else 0.0)
                best = (score, off + shift, mapping, fit)
    return best[0], best[1], best[2]
