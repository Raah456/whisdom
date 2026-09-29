"""Read the Marvel Tokon HUD out of a PS5 gameplay capture.

Calibrated 2026-08-21 against a 15-minute 1080p60 capture. At t = 510 s the left
Skill Gauge bar showed five lit segments and the number printed beside it read
125; the right showed four-and-a-part and read 110. So:

    one segment = 25 gauge, a full six-segment bar = 150

which is exactly the Skill Gauge model the reference tool already uses. Reading
the lit WIDTH of the bar is far steadier than recognising the digits, so that is
what this does.

Measured geometry (1920x1080):

    P1 gauge segments start at x = 604, 671, 727, 782, 838   (pitch ~55, width ~53)
    P2 gauge segments start at x = 1029, 1085, 1140, 1195
    both bands                     y = 1022..1048
    Assemble stars (3 slots each)  y = 58..92, x ~ 680..1240, gold = charged

KNOWN LIMITS, do not paper over them:
  * The star reader is NOT trustworthy yet. The icons animate, so naive colour
    thresholding reported 227 Assemble spends in 350 seconds of footage, which is
    nonsense. Debouncing to "a reading must hold 1.0 s" cuts it to ~22 with refill
    gaps clustering at 1-7 s, but the two players disagree over the same window.
    No Assemble regen number should be published off this until the star is
    template-matched instead of colour-thresholded.
  * Online footage carries rollback (0-3 rolled-back frames, continuously). NEVER
    measure frame-precise timing from it. Economy and behaviour only; timing comes
    from training mode.
  * Reading a large capture off an external drive stalls. Process in segments and
    checkpoint.

Usage:
    python hud.py CAPTURE.mp4 10 0 900 out.csv     # fps, start, duration, output
"""
import subprocess
import sys

import numpy as np

GW, GH, GY = 780, 28, 1022      # gauge band: x 600..1380
SW, SH, SY = 560, 34, 58        # star band:  x 680..1240
FULL = 315.0                    # lit columns in a full six-segment bar


def extract(video, fps, start, duration, out_path):
    frame_bytes = GW * (GH + SH) * 3
    cmd = [
        "ffmpeg", "-v", "error", "-ss", str(start), "-t", str(duration), "-i", video,
        "-filter_complex",
        f"[0:v]fps={fps},crop={GW}:{GH}:600:{GY},pad={GW}:{GH + SH}[a];"
        f"[0:v]fps={fps},crop={SW}:{SH}:680:{SY},pad={GW}:{SH}[b];[a][b]overlay=0:{GH}",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=frame_bytes * 4)
    out = open(out_path, "w")
    out.write("t,gauge_p1,gauge_p2,assemble_p1,assemble_p2\n")
    n = 0
    while True:
        buf = proc.stdout.read(frame_bytes)
        if len(buf) < frame_bytes:
            break
        img = np.frombuffer(buf, np.uint8).reshape(GH + SH, GW, 3).astype(np.int16)
        bar, stars = img[:GH], img[GH:]

        r, g, b = bar[..., 0], bar[..., 1], bar[..., 2]
        lit_p1 = (((r > 150) & (g > 70) & (b < 110) & (r - b > 70)).mean(0) > 0.5)
        lit_p2 = (((b > 150) & (g > 110) & (r < 130)).mean(0) > 0.5)
        gauge_p1 = round(lit_p1[:390].sum() / FULL * 150)
        gauge_p2 = round(lit_p2[425:].sum() / FULL * 150)

        sr, sg, sb = stars[..., 0], stars[..., 1], stars[..., 2]
        gold = (((sr > 170) & (sg > 130) & (sb < 110)).mean(0) > 0.3)
        runs, run = [], 0
        for i, on in enumerate(gold):
            if on:
                run += 1
            elif run:
                if 8 < run < 40:
                    runs.append(i - run)
                run = 0
        if 8 < run < 40:
            runs.append(len(gold) - run)
        asm_p1 = sum(1 for x in runs if x < 280)
        asm_p2 = sum(1 for x in runs if x >= 280)

        out.write(f"{float(start) + n / fps:.2f},{gauge_p1},{gauge_p2},{asm_p1},{asm_p2}\n")
        n += 1
        if n % 500 == 0:
            out.flush()
    out.close()
    return n


def debounce(values, hold=10):
    """A reading must persist `hold` samples before it is believed. At 10 fps
    that is one second, which is what makes the star channel merely bad rather
    than useless."""
    stable, current, run = [], values[0], 0
    for v in values:
        if v == current:
            run += 1
        else:
            current, run = v, 1
        stable.append(current if run >= hold else (stable[-1] if stable else current))
    return stable


if __name__ == "__main__":
    video, fps, start, duration, out_path = sys.argv[1:6]
    count = extract(video, float(fps), start, duration, out_path)
    print(f"{count} samples -> {out_path}")
