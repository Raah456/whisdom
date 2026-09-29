"""Read the two character name plates at the top of the screen.

Every record produced so far says "left" and "right". Nothing can be addressed
to a person — or to a character's kit — until those become "Magik" and
"Ghost Rider". This is the last gap in the chain from capture to a coach claim.

The plate is fixed-position, unanimated, and the roster is a CLOSED SET of 23
names, which is the ideal case for OCR: tesseract only has to get close, because
the answer is then snapped to the nearest roster entry. A read that is not close
to any of the 23 is refused rather than guessed.

Polarity varies — the name is dark on a light banner on some stages and light on
dark on others — so the mask is local contrast (|pixel − local blur|), which does
not care which way round it is.
"""
import json
import pathlib
import re
import subprocess
import tempfile

import cv2
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "tokon_plate"
SCRATCH.mkdir(exist_ok=True)

# x, y, w, h — generous, because names run from "HULK" to "CAPTAIN AMERICA"
PLATE = {"L": (200, 26, 380, 34), "R": (1326, 26, 392, 34)}

ROSTER = ["Captain America", "Peni Parker", "Carnage", "Champion", "Star-Lord",
          "Loki", "Danger", "Magneto", "Doctor Doom", "Hulk", "Ms. Marvel",
          "Green Goblin", "Deadpool", "Magik", "Ghost Rider", "Spider-Man",
          "Black Panther", "Storm", "Iron Man", "Blade", "Wolverine"]
_KEY = {re.sub(r"[^A-Z]", "", n.upper()): n for n in ROSTER}


def _mask(bgr):
    """The glyph's OUTLINE, which is near-white and thick on every stage.

    Local contrast was tried first and is noise here — the stages are textured
    enough that |pixel - blur| lights up the whole crop. The name is drawn dark
    with a heavy white outline, and that outline is the one thing that does not
    change with the stage behind it, so mask on it directly."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 1] < 70) & (hsv[..., 2] > 185)).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))


def _glyphs(m):
    """Keep only components that look like letters of this name, on one baseline.

    Cropping to every masked pixel pulled in bright sky and pale architecture at
    the edges of the plate, and tesseract dutifully read that as extra letters:
    "GHOSTIRIDER", "LOMAGIKG", "TTAGIKNG". The letters are a known size and share
    a baseline; nothing else in the crop does."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    # The glyphs' white outlines TOUCH, so a word is not letters — it is one or
    # two wide blobs ("GHOST" + "RIDER", 105x28 and 96x28). A per-letter width
    # cap deleted the entire name. Filter on the height of the text line and on
    # being substantial; width is whatever the word happens to be.
    cand = [(stats[i][0], stats[i][1], stats[i][2], stats[i][3], i)
            for i in range(1, n)
            if 16 <= stats[i][3] <= 32 and stats[i][2] >= 18 and stats[i][4] >= 120]
    if not cand:
        return None
    tops = sorted(c[1] for c in cand)
    base = tops[len(tops) // 2]
    keep = [c for c in cand if abs(c[1] - base) <= 7]
    if not keep:
        return None
    out = np.zeros_like(m)
    for _, _, _, _, i in keep:
        out[lab == i] = 1
    return out


def _ocr(bgr):
    m = _glyphs(_mask(bgr))
    if m is None:
        return ""
    ys, xs = np.nonzero(m)
    if len(xs) < 80:
        return ""
    a, b, c, d = ys.min(), ys.max(), xs.min(), xs.max()
    if (b - a) < 8 or (d - c) < 20:
        return ""
    tight = m[a:b+1, c:d+1] * 255
    big = cv2.resize(255 - tight, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    big = cv2.copyMakeBorder(big, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)
    tmp = SCRATCH / "p.png"
    cv2.imwrite(str(tmp), big)
    out = subprocess.run(
        ["tesseract", str(tmp), "-", "--psm", "7", "-c",
         "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ.- "],
        capture_output=True, text=True).stdout
    tmp.unlink(missing_ok=True)
    return re.sub(r"[^A-Z]", "", out.upper())


def _snap(key, max_edits=2):
    """Nearest roster name, or None.

    The closed set is what makes a near-miss safe: 'DOCTORDOOK' is one edit from
    DOCTORDOOM and nothing else. But it is only safe if the read is SUBSTANTIAL.
    A three-letter scrap of noise, 'FUL', is two edits from HULK and was snapped
    to Hulk with full confidence — a fabricated character in the record. So a
    read must be at least 4 characters AND within 25% of the target's length
    before the closed set is allowed to rescue it."""
    if not key or len(key) < 4:
        return None
    if key in _KEY:
        return _KEY[key]
    scored = sorted((_edit(key, k), k) for k in _KEY
                    if abs(len(k) - len(key)) <= max(2, len(k) // 4))
    if not scored or scored[0][0] > min(max_edits, len(key) // 4 + 1):
        return None
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return _KEY[scored[0][1]]


def _edit(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + (ca != cb)))
        prev = cur
    return prev[-1]


def read(img):
    """{'L': name or None, 'R': name or None}."""
    out = {}
    for side, (x, y, w, h) in PLATE.items():
        out[side] = _snap(_ocr(img[y:y+h, x:x+w]))
    return out


def frame_at(video, t):
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video,
                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                       capture_output=True)
    n = 1920 * 1080 * 3
    return None if len(p.stdout) < n else np.frombuffer(p.stdout[:n], np.uint8).reshape(1080, 1920, 3)


# ------------------------------------------------------------- templates ---
# STATUS 2026-08-22 (b) — 6 characters templated, 41 templates.
#   Magik 14, Doctor Doom 7, Captain America 5, Storm 5, Spider-Man 3,
#   Ghost Rider 2. Star-Lord appears in segment 21 and has NO template yet.
#
# Why so many templates per name: the outline mask produces two visually
# distinct variants of the same word — an "outline" form where the letter rings
# stay separate, and a "filled" form where they merge into solid blobs — plus
# fragments when a long name is split ("CAPTAIN" and "AMERICA" cluster
# separately). Clustering 670 bitmaps gave 277 clusters, so the bank carries
# every variant rather than pretending one canonical shape exists.
#
# Classification is by NAME, not by template: take the minimum distance within
# each name, then require a margin between the best name and the second-best.
# A margin between two templates of the SAME name is meaningless.
NORM = (32, 200)                      # h, w every name bitmap is squashed to
PLATE_TEMPLATES = HERE / "plate_words.npz"


def word_bitmap(img, side):
    """Normalised bitmap of one plate's name, or None."""
    x, y, w, h = PLATE[side]
    m = _glyphs(_mask(img[y:y+h, x:x+w]))
    if m is None:
        return None
    ys, xs = np.nonzero(m)
    if len(xs) < 120:
        return None
    a, b, c, d = ys.min(), ys.max(), xs.min(), xs.max()
    if (b - a) < 12 or (d - c) < 30:
        return None
    return cv2.resize(m[a:b+1, c:d+1].astype(np.float32), (NORM[1], NORM[0]),
                      interpolation=cv2.INTER_AREA)


def load_plate_templates(path=PLATE_TEMPLATES):
    z = np.load(path)
    return {k: z[k] for k in z.files}


def _name_of(key):
    """Template keys are "<Name>#<variant>". The variant is not the answer."""
    return re.sub(r"#\d+$", "", key)


def read_template(img, tpl, max_dist=0.13, min_margin=0.02):
    """{'L': name or None, 'R': name or None} by template match.

    Unrecognised is None, never a guess: a plate that cannot be read leaves the
    record saying "left", which downstream code already handles.

    RANKED BY NAME, NOT BY TEMPLATE. The bank holds up to 14 templates of the
    same word (outline vs filled, and fragments of split names), so the two
    closest templates are usually two variants of the SAME character — a margin
    between those is meaningless, and comparing them refused half the plates it
    could read. Magik reads as "Magik#1" and a second Magik variant sits 0.001
    behind it, so the margin test rejected a correct read. Take the minimum
    distance WITHIN each name, then require the margin between the best name and
    the best OTHER name.

    Measured against the 25 LongBatch1 segments whose plates were read by eye
    (50 plates): template-ranked reads 23 and gets 22 right; name-ranked reads
    25 and gets 24 right. The one wrong read is the same in both — segment 11's
    right plate, where a tag happened mid-segment. So the fix is worth two
    plates and costs nothing, and the honest headline is that a single frame
    reads only half the plates. `read_plates()` below is the answer to that."""
    out = {}
    for side in ("L", "R"):
        bm = word_bitmap(img, side)
        if bm is None:
            out[side] = None
            continue
        best = {}
        for k, t in tpl.items():
            d = float(np.abs(bm - t).mean())
            nm = _name_of(k)
            if nm not in best or d < best[nm]:
                best[nm] = d
        ranked = sorted((d, nm) for nm, d in best.items())
        if not ranked:
            out[side] = None
            continue
        d0, name = ranked[0]
        d1 = ranked[1][0] if len(ranked) > 1 else 9.9
        out[side] = name if (d0 <= max_dist and d1 - d0 >= min_margin) else None
    return out


def read_plates(video, a, b, tpl, at=(0.25, 0.4, 0.55, 0.7, 0.85)):
    """The plate at several moments in a segment, voted.

    One read is one moment: a tag mid-segment, a hit-spark over the plate or a
    transition wipe all break it, and a single failed read leaves the side
    unnamed for the whole segment. Reading five moments and keeping the counts
    gives the point character (the most-seen name) AND the evidence that a tag
    happened (more than one name on a side), which is what `_seen` is for.

    Measured against the 25 LongBatch1 segments read by eye (50 plates):
      one frame, ranked by template   23 read, 22 right, 1 wrong
      one frame, ranked by name       25 read, 24 right, 1 wrong
      five frames, voted              38 read, 38 right, 0 wrong
    The vote also FIXES the wrong one: segment 11's right plate reads Magik at
    40% and Captain America at three other moments, because a tag happened
    there — `_seen` says {"Magik": 1, "Captain America": 2} and the record now
    carries that instead of a confident single wrong name. The 12 plates still
    unread are almost all the LEFT plate on stages where the banner washes the
    mask out, plus Star-Lord, who has no template in the bank at all.

    Returns {'L': name|None, 'R': name|None, '_seen': {'L': {name: n}, ...},
    '_reads': n}."""
    seen = {"L": {}, "R": {}}
    n = 0
    for frac in at:
        img = frame_at(video, a + frac * (b - a))
        if img is None:
            continue
        n += 1
        got = read_template(img, tpl)
        for side in ("L", "R"):
            if got[side]:
                seen[side][got[side]] = seen[side].get(got[side], 0) + 1
    out = {"_seen": seen, "_reads": n}
    for side in ("L", "R"):
        ranked = sorted(seen[side].items(), key=lambda kv: -kv[1])
        # ONE READ IS NOT A NAME. Match2's left plate read "Storm" once in five
        # tries and the coach narrated a Storm matchup; the fighter on screen was
        # Star-Lord, who has no template in the bank, so the ranker force-matched
        # him to the nearest known word. Two agreeing reads before a side gets a
        # name; the counts stay in _seen either way, so a human can still look.
        out[side] = ranked[0][0] if ranked and ranked[0][1] >= 2 else None
    return out
