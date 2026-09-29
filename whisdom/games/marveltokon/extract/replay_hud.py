"""Read the Marvel Tokon REPLAY-PLAYBACK overlay.

STATUS 2026-08-22 (b) — revalidated on LongBatch1.mp4, a capture the geometry
was never tuned for, which is the first evidence any of this generalises.

    frame-data panels   WORKING. panel_data() reads them by TEMPLATE.
                        Hand-checked exact on both sides. Against tesseract over
                        37 frames x 2 sides x 7 fields: 330 agree, 11 conflict —
                        and on every one of the 11, eyes-on adjudication went to
                        the template reader. tesseract lost 11/11.
                        27 fields (7.3%) are refused rather than guessed.
                        2.5 ms per frame for both sides, against 353 ms.
                        frame_data() (tesseract) is kept only as the bootstrap
                        labeller for build_panel_templates(); do not read data
                        with it.
    input frame counts  WORKING. Re-checked on LongBatch1: left 14/16 exact,
                        right 16/17 exact, ZERO wrong values, all misses refused.
    input DIRECTIONS    *** NOT WORKING — 3/8 on the one frame tested. ***
                        read_direction() is OFF by default in input_rows() and
                        must stay off. Three geometries were tried (fixed box,
                        outline-centroid, 3x3 grid over the outline bbox) and
                        none converged. The deeper problem is the TEST:
                        "expected" values were eyeballed off a scaled montage,
                        so a failure might be the reader or the expectation.
                        Next attempt needs real ground truth first — see T-014.

Replay playback shows, for both players at once, what live footage never did:

    Damage / Combo / Highest Combo
    Recovery / Active / Attack Startup / Total
    an input history column carrying a FRAME COUNT beside every input

and it carries no rollback, because playback is deterministic local simulation.
That combination is what makes move-level coaching a parsing problem rather than
a computer-vision one. See `TOKON_REPLAY_HUD.md`.

Measured on Vid1.mp4 (1920x1080):

    frame-data panels   left  x 225..770,  right x 1175..1720,  y 195..615
    input gutter        left  x  20..80    (numerals, right-aligned at x~59-70)
    input glyphs        left  x  78..175   (d-pad rosette, then button glyphs)
    row pitch           42 px, rows land on a stable grid

Numerals are white on wildly varying game backgrounds, so a global threshold is
useless — mask on saturation/value instead, which removes the background
completely and leaves clean glyphs.

Digits are read by TEMPLATE, not OCR. Tesseract manages ~87% on these and its
mistakes are silent; the font is fixed, so templates bootstrapped from
high-confidence OCR reach exactness. `build_templates()` does that bootstrap.
"""
import json
import pathlib
import re
import subprocess
import tempfile

import cv2
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATES = HERE / "digit_templates.npz"

# Scratch MUST live off the mounted folder. The device bridge forbids deletes,
# so a temp file written next to this module can never be cleaned up.
SCRATCH = pathlib.Path(tempfile.gettempdir()) / "tokon_hud"
SCRATCH.mkdir(exist_ok=True)

PANEL = {"L": (225, 195, 545, 420), "R": (1175, 195, 545, 420)}
GUTTER = {"L": (20, 140, 60, 800), "R": (1840, 140, 60, 800)}
# the d-pad rosette sits just right of the numerals (mirrored on the right side)
ROSETTE_SPAN = {"L": (74, 122), "R": (1798, 1846)}   # x0, x1 of the rosette gutter
BUTTONS = {"L": (122, 56), "R": (1742, 56)}
ROW_PITCH = 42

FIELDS = ("Damage", "Combo", "Highest Combo",
          "Recovery", "Active", "Attack Startup", "Total")


# ---------------------------------------------------------------- masking ---
def white_mask(bgr):
    """Isolate the overlay's white text from the game behind it."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 1] < 55) & (hsv[..., 2] > 195)).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


# ------------------------------------------------------------ frame data ---
def frame_data(img, side):
    """The seven labelled numbers on one side. Values may be None (shown as '-')."""
    x, y, w, h = PANEL[side]
    g = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
    g = cv2.resize(g, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    tmp = SCRATCH / f"fd_{side}.png"
    cv2.imwrite(str(tmp), g)
    txt = subprocess.run(["tesseract", str(tmp), "-", "--psm", "6"],
                         capture_output=True, text=True).stdout
    tmp.unlink(missing_ok=True)
    out = {}
    for field in FIELDS:
        # "Recovery -15(-15)" -> -15 ; "Active -" -> None
        m = re.search(rf"{field}\s+(-?\d+)(?:\((-?\d+)\))?", txt)
        out[field] = int(m.group(1)) if m else None
    return out


# ---------------------------------------------------------------- digits ---
def digit_blobs(img, side):
    """Every numeral blob in the input gutter, as (x, y, w, h, bitmap)."""
    x, y, w, h = GUTTER[side]
    m = white_mask(img[y:y + h, x:x + w])
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        bx, by, bw, bh, area = stats[i]
        if not (18 < area < 900 and 6 < bh < 34 and 3 < bw < 40):
            continue
        bmp = (lab[by:by + bh, bx:bx + bw] == i).astype(np.uint8) * 255
        out.append((bx, by + y, bw, bh, bmp))
    return out


# numpad notation, as the wiki writes it: 5 is neutral, 6 is toward the
# opponent. The rosette lights the pressed direction in amber, so direction is
# the centroid of the amber pixels relative to the rosette's centre — no
# templates needed, and it reads diagonals for free.
DIRS = {(0, 0): 5, (1, 0): 6, (-1, 0): 4, (0, -1): 8, (0, 1): 2,
        (1, -1): 9, (-1, -1): 7, (1, 1): 3, (-1, 1): 1}


def amber_mask(bgr):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    return ((hsv[..., 0] > 5) & (hsv[..., 0] < 34) &
            (hsv[..., 1] > 110) & (hsv[..., 2] > 140)).astype(np.uint8)


def read_direction(img, side, y, pitch=ROW_PITCH):
    """Numpad direction for the row at `y`, or None if it cannot be called.

    Self-calibrating: the rosette draws itself with a pale outline, so the
    outline's bounding box *is* the reference frame. Hard-coding a box was tried
    and kept drifting — the glyph does not sit where eyeballing a scaled
    screenshot suggests. Measuring it per row costs nothing and cannot drift.
    """
    x0, x1 = ROSETTE_SPAN[side]
    y0, y1 = max(y - 8, 0), y + pitch - 4
    box = img[y0:y1, x0:x1]
    if box.size == 0:
        return None
    hsv = cv2.cvtColor(box, cv2.COLOR_BGR2HSV)
    outline = (hsv[..., 1] < 70) & (hsv[..., 2] > 170)
    ys, xs = np.nonzero(outline)
    if len(xs) < 40:
        return None                       # no rosette drawn on this row
    cx0, cx1, cy0, cy1 = xs.min(), xs.max(), ys.min(), ys.max()
    if (cx1 - cx0) < 12 or (cy1 - cy0) < 12:
        return None
    ctr_x, ctr_y = (cx0 + cx1) / 2.0, (cy0 + cy1) / 2.0
    rad_x, rad_y = max((cx1 - cx0) / 2.0, 1), max((cy1 - cy0) / 2.0, 1)

    m = amber_mask(box)
    m[:, :max(cx0 - 2, 0)] = 0            # ignore amber outside the rosette
    m[:, min(cx1 + 3, m.shape[1]):] = 0
    m[:max(cy0 - 2, 0), :] = 0
    m[min(cy1 + 3, m.shape[0]):, :] = 0
    n = int(m.sum())
    if n < 10:
        return 5                          # rosette drawn but unlit -> neutral
    # Which third of the rosette holds the lit petal? A centroid was tried and
    # drifted — the arrow glyph is drawn off-centre inside its petal, so small
    # errors in the reference centre flipped diagonals. Summing amber into a
    # 3x3 grid over the outline's own bounding box is insensitive to that.
    sub = m[cy0:cy1 + 1, cx0:cx1 + 1]
    if sub.size == 0:
        return None
    gh, gw = sub.shape[0] / 3.0, sub.shape[1] / 3.0
    grid = np.zeros((3, 3), np.int32)
    for gy in range(3):
        for gx in range(3):
            cell = sub[int(gy * gh):int((gy + 1) * gh), int(gx * gw):int((gx + 1) * gw)]
            grid[gy, gx] = int(cell.sum())
    NUMPAD = ((7, 8, 9), (4, 5, 6), (1, 2, 3))
    gy, gx = np.unravel_index(int(np.argmax(grid)), grid.shape)
    if grid[gy, gx] < 6:
        return 5
    return NUMPAD[gy][gx]


def norm(bmp, size=(16, 24)):
    return cv2.resize(bmp, size, interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0


def group_rows(blobs, pitch=ROW_PITCH):
    """Blobs -> rows, ordered top to bottom, digits left to right within a row."""
    rows, cur = [], []
    for b in sorted(blobs, key=lambda b: b[1]):
        if cur and b[1] - cur[-1][1] > pitch * 0.35:
            rows.append(sorted(cur, key=lambda b: b[0])); cur = []
        cur.append(b)
    if cur:
        rows.append(sorted(cur, key=lambda b: b[0]))
    return rows


# ------------------------------------------------------------- templates ---
def build_templates(video, samples=40, start=20, end=280, out=TEMPLATES):
    """Bootstrap digit templates: tesseract labels the easy blobs, and those
    become the templates that then read the hard ones. Only high-confidence
    single-digit rows are used as seeds, so a silent OCR error cannot poison
    the set."""
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    banks = {}
    for i in range(samples):
        t = start + (end - start) * i / max(samples - 1, 1)
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        for side in ("L", "R"):
            for row in group_rows(digit_blobs(frame, side)):
                if not 1 <= len(row) <= 2:
                    continue
                # render the whole row as one clean image and read it; a result
                # is only trusted when its digit count matches the blob count,
                # which is what lets 0 and 8 be seeded from two-digit numbers
                pad = 6
                hgt = max(b[3] for b in row)
                strip = np.zeros((hgt, sum(b[2] for b in row) + pad * (len(row) - 1)),
                                 np.uint8)
                cx = 0
                for b in row:
                    strip[0:b[3], cx:cx + b[2]] = b[4]
                    cx += b[2] + pad
                big = cv2.resize(255 - strip, None, fx=6, fy=6,
                                 interpolation=cv2.INTER_CUBIC)
                big = cv2.copyMakeBorder(big, 24, 24, 24, 24,
                                         cv2.BORDER_CONSTANT, value=255)
                tmp = SCRATCH / "d.png"
                cv2.imwrite(str(tmp), big)
                psm = "10" if len(row) == 1 else "7"
                tsv = subprocess.run(
                    ["tesseract", str(tmp), "-", "--psm", psm, "-c",
                     "tessedit_char_whitelist=0123456789", "tsv"],
                    capture_output=True, text=True).stdout
                read, conf = "", 0.0
                for line in tsv.splitlines()[1:]:
                    f = line.split("\t")
                    if len(f) >= 12 and f[11].strip().isdigit():
                        read += f[11].strip(); conf = max(conf, float(f[10]))
                if len(read) == len(row) and conf >= 80:
                    for b, ch in zip(row, read):
                        banks.setdefault(ch, []).append(norm(b[4]))
    cap.release()
    # merge with whatever is already known — templates accumulate across runs,
    # so a digit that is rare in one stretch of video can be picked up in another
    tpl = {}
    if pathlib.Path(out).exists():
        z = np.load(out)
        tpl = {k: z[k] for k in z.files}
    for d, v in banks.items():
        fresh = np.mean(v, axis=0)
        tpl[d] = fresh if d not in tpl else (tpl[d] + fresh) / 2.0
    np.savez(out, **tpl)
    return {d: len(v) for d, v in sorted(banks.items())}


def load_templates(path=TEMPLATES):
    z = np.load(path)
    return {k: z[k] for k in z.files}


# A confident match scores around -30 with the runner-up 90+ behind it. A blob
# degraded by a bright background scores -130 with a margin of 7 — a coin flip.
# Guessing there is how silent errors get into the data, so it reports "?".
MIN_MARGIN = 25.0
MAX_DIST = 95.0


def read_digit(bmp, tpl):
    """(digit, margin) — digit is None when the read is not trustworthy."""
    v = norm(bmp)
    ranked = sorted(((-float(np.abs(v - t).sum()), d) for d, t in tpl.items()),
                    reverse=True)
    (best_score, best), (second_score, _) = ranked[0], ranked[1]
    margin = best_score - second_score
    if margin < MIN_MARGIN or best_score < -MAX_DIST:
        return None, margin
    return best, margin


def input_rows(img, side, tpl, directions=False):
    """[(y, frame_count_or_None)] for the input history column on one side.

    A row whose digits could not be read confidently comes back as None rather
    than a plausible-looking number. Downstream code must handle that; a wrong
    frame count is worse than a missing one.

    `directions` is OFF by default because read_direction() is known broken
    (3/8 on the one frame tested). Turning it on puts unvalidated values into
    the output; do not, until T-014 gives it real ground truth."""
    out = []
    for row in group_rows(digit_blobs(img, side)):
        digits = [read_digit(b[4], tpl)[0] for b in row]
        y = row[0][1]
        frames = int("".join(digits)) if all(d is not None for d in digits) else None
        rec = {"y": y, "frames": frames}
        if directions:
            rec["direction"] = read_direction(img, side, y)
        out.append(rec)
    return out


# ------------------------------------------------------- panel by template ---
# frame_data() above shells out to tesseract: ~350 ms per frame for both sides,
# and its mistakes are silent. Over a 23-minute batch that is 16 minutes of OCR
# for numbers in a FIXED font at FIXED positions. Read them the same way the
# input gutter is read - by template, with a confidence gate that refuses rather
# than guesses - and the same work costs about a millisecond.
#
# Rows sit on a stable y grid inside the panel (measured on both sides of two
# different captures). Values are right-aligned in a window that stops short of
# the panel's edge decoration, which is what the x cap is for: without it the
# right-hand panel picks up stage art sitting past the plate.
PANEL_ROWY = (35, 68, 100, 282, 312, 341, 371)     # glyph top, per FIELDS
PANEL_VAL_X = (300, 515)                            # value zone within the panel
PANEL_TEMPLATES = HERE / "panel_templates.npz"


def panel_blobs(img, side):
    """[(field, [glyph blobs], leading_minus)] - the value glyphs, per row.

    The panel plate is light and its text is dark, but the plate is
    semi-transparent so its absolute brightness follows the stage behind it.
    Threshold against a local blur instead of a constant: what is stable is
    that the text is darker than its immediate surroundings.

    The minus sign is handled separately and on purpose. Measured, it is 6x2 to
    6x4 pixels - and any size filter loose enough to admit that also admits the
    background speckle that shows through the plate (a single frame carries two
    dozen 1x1 blobs). Dropping it is not cosmetic: "-52(-52)" would come back as
    blobs "52(52)" and parse as POSITIVE 52, a silent sign flip on the one field
    that means frame advantage. So it is looked for in the one place it can
    legitimately be - immediately left of the leftmost digit, at that digit's
    vertical midpoint - which is context no speckle can imitate.
    """
    x, y, w, h = PANEL[side]
    g = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY).astype(np.float32)
    dark = ((cv2.blur(g, (31, 31)) - g) > 18).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(dark, 8)
    x0, x1 = PANEL_VAL_X
    cand, dashes = [], []
    for i in range(1, n):
        bx, by, bw, bh, area = stats[i]
        if not (x0 <= bx and bx + bw <= x1):
            continue
        if 20 < area < 1200 and 8 < bh < 34 and 2 < bw < 30:
            cand.append((bx, by, bw, bh,
                         (lab[by:by + bh, bx:bx + bw] == i).astype(np.uint8) * 255))
        elif bh <= 6 and 3 <= bw <= 22 and area >= 8 and bw >= 1.5 * bh:
            dashes.append((bx, by, bw, bh))

    out = []
    for field, ry in zip(FIELDS, PANEL_ROWY):
        row = sorted((b for b in cand if ry - 5 <= b[1] <= ry + 5), key=lambda b: b[0])
        marks = []
        if row:
            mid = row[0][1] + row[0][3] / 2.0
            lo, hi = row[0][0] - 20, row[-1][0] + row[-1][2]
            marks = sorted(dx for dx, dy, dw, dh in dashes
                           if lo <= dx and dx + dw <= hi
                           and abs(dy + dh / 2.0 - mid) <= 6)
        out.append((field, row, marks))
    return out


def read_panel_string(row, tpl, marks=()):
    """The raw value string of one row, e.g. "-46(-1)", or None.

    The parenthesised copy is USUALLY the same number - but not always:
    "Recovery -46(-1)" is real, observed at 2214 s. So the two are different
    quantities and the second one is information. What they MEAN is open
    (T-011/T-015).

    Minus signs are placed by x position rather than classified, because they
    are 6x3 px and no size filter that admits them excludes background speckle.
    Detecting only the LEADING one made "-10(-10)" render as "-10(10)", which
    reads as two different numbers - a fake finding manufactured by the reader.
    Interleaving every dash in the row by position is what stops that."""
    items = [(b[0], None, b) for b in row] + [(x, "-", None) for x in marks]
    chars = []
    for _, mark, b in sorted(items, key=lambda i: i[0]):
        if mark:
            chars.append("-")
            continue
        c, _ = read_digit(b[4], tpl)
        if c is None:
            return None
        chars.append(c)
    return "".join(chars)


def read_panel_row(row, tpl, marks=()):
    """The leading integer of one value row, or None if it cannot be read.

    "0(0)" and "-15(-15)" show the value twice - the parenthesised copy is the
    same number, so everything from the first '(' is dropped. A row that is just
    '-' means the field does not apply to this move and is None, which is a
    different thing from a row that could not be read - but both are None to the
    caller, because neither is a number."""
    raw = read_panel_string(row, tpl, marks)
    if raw is None:
        return None
    head = raw.split("(")[0]
    return int(head) if re.match(r"^-?\d+$", head) else None


def panel_data(img, side, tpl, raw=False):
    """frame_data() by template: same seven fields, ~350x faster, no tesseract.

    With raw=True, also returns "<field> raw" entries carrying the value string
    exactly as printed, parentheses included."""
    out = {}
    for field, row, marks in panel_blobs(img, side):
        v = read_panel_row(row, tpl, marks) if row else None
        # Only Recovery can be negative - it is a signed advantage. Damage, a
        # combo total and a startup count cannot be. A negative here is not a
        # small error, it is proof the sign was manufactured (a speckle read as
        # a minus), so refuse the field rather than pass an impossible number
        # downstream. Caught eight of these in one 45-second segment.
        if v is not None and v < 0 and field != "Recovery":
            v = None
        out[field] = v
        if raw:
            out[field + " raw"] = read_panel_string(row, tpl, marks) if row else None
    return out


def build_panel_templates(video, times, out=PANEL_TEMPLATES):
    """Bootstrap the panel bank with tesseract as the labeller.

    A row is only used as a seed when the blob count matches the length of what
    tesseract read, which is the check that stops a silent OCR error becoming a
    permanently wrong template. Recovery seeds '(' and ')' as well, since it is
    the one field that prints its value twice."""
    banks = {}
    for t in times:
        img = _frame_at(video, t)
        if img is None:
            continue
        for side in ("L", "R"):
            fd = frame_data(img, side)
            for field, row, _marks in panel_blobs(img, side):
                v = fd.get(field)
                if v is None or not row:
                    continue
                for expect in (str(v), f"{v}({v})"):
                    if len(expect) == len(row):
                        for b, ch in zip(row, expect):
                            banks.setdefault(ch, []).append(norm(b[4]))
                        break
    tpl = {}
    if pathlib.Path(out).exists():
        z = np.load(out)
        tpl = {k: z[k] for k in z.files}
    for d, v in banks.items():
        fresh = np.mean(v, axis=0)
        tpl[d] = fresh if d not in tpl else (tpl[d] + fresh) / 2.0
    np.savez(out, **tpl)
    return {d: len(v) for d, v in sorted(banks.items())}


def _frame_at(video, t):
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True)
    n = 1920 * 1080 * 3
    return None if len(p.stdout) < n else np.frombuffer(p.stdout[:n], np.uint8).reshape(1080, 1920, 3)
