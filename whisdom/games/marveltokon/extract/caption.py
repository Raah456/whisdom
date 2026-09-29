"""Read the game's own judgement caption.

STATUS 2026-08-22
    banner detection   WORKING. Teal, unmistakable.
    Punish! reading    WORKING at distance <= 0.16, with a KNOWN SIDE BIAS —
                       see "The right-side bias" below. 10 read from 17.1 min,
                       all ten confirmed by eye. Treat as a LOWER BOUND.
    other words        Good!, Knockdown!, Slam!, Big damage! are legible and
                       templated, but only Punish! has been validated.

Every judgement the game prints — Knockdown, Punish!, Counter!, Good! — uses the
SAME teal banner. Detecting the banner therefore detects ALL of them, which is
exactly why a "knockdown detector" built on banner colour alone agreed with hand
labels only 2 of 6: it was firing on every caption in the game.

The banner is the container. The WORD inside it is the meaning.

The word is white bold ITALIC, which tesseract reads as noise ("aon"). It is a
closed set of a few captions in a fixed font, so it is template-matched — the
same move that beat tesseract on the panel digits.
"""
import subprocess
import numpy as np
import cv2

BAND = (0, 655, 1920, 230)          # x, y, w, h — captions sit here, either side
NORM = (48, 160)                    # h, w that every word bitmap is squashed to


def teal(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return ((hsv[..., 0] > 82) & (hsv[..., 0] < 100) &
            (hsv[..., 1] > 110) & (hsv[..., 2] > 110)).astype(np.uint8)


def banners(img, min_w=90):
    """[(x0, x1, y0, y1)] of teal banner BLOBS in the band.

    Column ranges were tried first and were wrong: the right-hand banner's
    column span runs to the screen edge, so the crop swallowed the input-history
    column and every word bitmap carried a different clutter of button glyphs
    beside it. 200 events then produced 174 clusters. Take the connected
    component instead — the banner is one solid teal shape and its own bounding
    box is the only honest crop.

    There can be two: a Counter! fires on both sides at once.
    """
    x, y, w, h = BAND
    m = teal(img[y:y+h, x:x+w])
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 25), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        bx, by, bw, bh, area = stats[i]
        if bw >= min_w and bh >= 22 and area > bw * bh * 0.35:
            out.append((int(bx), int(bx + bw), int(by), int(by + bh)))
    return sorted(out)


def word_bitmap(img, span, norm=NORM):
    """Text = the NOT-TEAL holes inside the teal banner.

    The banner is teal and the glyphs are white with a white outline. Masking on
    brightness fights glare and whatever the stage is doing behind, and produced
    bitmaps so degraded that template matching gave margins of 0.006 — a coin
    flip. Masking on "inside the banner but not teal" uses the banner itself as
    the reference, which glare cannot move."""
    x, y, w, h = BAND
    x0, x1, y0, y1 = span
    sub = img[y+y0:y+y1, x+x0:x+x1]
    tsub = teal(sub)
    if tsub.sum() < 400:
        return None
    filled = cv2.morphologyEx(tsub, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
    txt = ((filled > 0) & (tsub == 0)).astype(np.uint8)
    txt = cv2.morphologyEx(txt, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    # The banner runs off the side of the screen, so its bounding box overlaps
    # the input-history gutter. Those digits are known UI sitting on top of the
    # banner, not part of the caption — blank them, or every right-hand word
    # carries a different tail of button glyphs and no two bitmaps match.
    for gx0, gx1 in ((0, 90), (1830, 1920)):
        a0, a1 = max(gx0 - (x + x0), 0), max(gx1 - (x + x0), 0)
        if a1 > 0 and a0 < txt.shape[1]:
            txt[:, a0:min(a1, txt.shape[1])] = 0
    ys, xs = np.nonzero(txt)
    if len(xs) < 200:
        return None
    a2, b2, c2, d2 = ys.min(), ys.max(), xs.min(), xs.max()
    if (b2 - a2) < 12 or (d2 - c2) < 30:
        return None
    return cv2.resize(txt[a2:b2+1, c2:d2+1].astype(np.float32),
                      (norm[1], norm[0]), interpolation=cv2.INTER_AREA)


def _word_bitmap_by_brightness(img, span):
    """Normalised white-text bitmap inside one banner, or None."""
    x, y, w, h = BAND
    x0, x1 = span
    crop = img[y:y+h, x+x0:x+x1]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    # white glyphs, but only where the banner actually is
    tl = teal(crop)
    near = cv2.dilate(tl, np.ones((25, 25), np.uint8))
    wm = (((hsv[..., 1] < 80) & (hsv[..., 2] > 165)) & (near > 0)).astype(np.uint8)
    wm = cv2.morphologyEx(wm, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    ys, xs = np.nonzero(wm)
    if len(xs) < 150:
        return None
    a, b, c, d = ys.min(), ys.max(), xs.min(), xs.max()
    if (b - a) < 12 or (d - c) < 30:
        return None
    tight = wm[a:b+1, c:d+1].astype(np.float32)
    return cv2.resize(tight, (NORM[1], NORM[0]), interpolation=cv2.INTER_AREA)


def read(img, tpl, max_dist=0.20, min_margin=0.035):
    """[(x0, word)] for every caption on screen. Unrecognised -> '?'."""
    out = []
    for span in banners(img):
        bm = word_bitmap(img, span)
        if bm is None:
            continue
        ranked = sorted((float(np.abs(bm - t).mean()), k) for k, t in tpl.items())
        if not ranked:
            out.append((span[0], "?"))
            continue
        (d0, w0) = ranked[0]
        d1 = ranked[1][0] if len(ranked) > 1 else 9.9
        out.append((span[0], w0 if (d0 <= max_dist and d1 - d0 >= min_margin) else "?"))
    return out


def frame_at(video, t):
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video,
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                       capture_output=True)
    n = 1920 * 1080 * 3
    return None if len(p.stdout) < n else np.frombuffer(p.stdout[:n], np.uint8).reshape(1080, 1920, 3)


# ---------------------------------------------------------------- findings ---
# THE RIGHT-SIDE BIAS. All ten Punish! captions read from the corpus are on the
# RIGHT. That is almost certainly the reader, not the players: the banner runs
# off the edge of the screen, so a LEFT-side caption is truncated at its start
# ("Knockdown!" reads as "nockdown!"), and templates cut from right-side
# examples will not match it. Until a left-side template set exists, the punish
# count is a LOWER BOUND and per-player punish counts must not be quoted.
#
# PUNISHES AND OPENINGS BARELY OVERLAP. Of 60 openings found by find_openings.py,
# exactly ONE has a Punish! caption within 1.5 s of its end; 8 of the 10 punishes
# have no detected opening in the preceding 3 s. These two signals are measuring
# different things. That is a result, not a bug: it says the Recovery-stopwatch
# windows are largely NOT the situations that produce punishes, which fits the
# eyes-on finding that many of them are knockdowns. It also means the caption is
# an INDEPENDENT signal and the more trustworthy of the two, because it is the
# game's own judgement rather than our inference.
#
# WHAT IS STILL UNKNOWN: whether the caption renders on the side of the player
# who punished or the player who got punished. Do not attribute a punish to a
# player until that is settled — one room match with a known-bad button press
# would settle it in minutes.
