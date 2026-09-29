"""
Footage clips — the receipt as a short video.

    python3 -m whisdom.games.marveltokon.app.clips LongBatch1 [--max N] [--menu] [--width W] [--redo]

For every finding the Replay screen shows (openings, Punish! reads) cut a
4-second clip that ends 0.8 s after the finding's timestamp, 640 px wide,
silent, H.264 → data/app/clips/<finding id, sanitised>.mp4. Skips clips that
already exist, so it can be run in slices (the device shell caps calls at ~45 s).
--width sets the clip width (default 1280 since build 12 — the Review deck shows
them big); --redo re-cuts clips that already exist.

--menu also cuts an 8-second loop for the menu hero from the first usable
segment where the profile's point character is on screen.

--music NAME START SECONDS cuts a BGM loop from the footage's audio track →
data/app/audio/NAME.m4a and NAME.ogg (a 1.5 s fade at both ends so the loop
seam is soft). Every file in data/app/audio shows up in the menu's BGM picker.
    python3 -m whisdom.games.marveltokon.app.clips LongBatch1 --music lobby 2210 75

Video is looked up in the repo root (where the .mp4 files live, gitignored),
then the external drive path used by the pipeline.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", "..", ".."))
DATA = os.path.normpath(os.path.join(HERE, "..", "data"))
OUT = os.path.join(DATA, "app", "clips")
VIDEO_DIRS = [ROOT, os.path.expanduser("~/mnt/Untitled/PS5/CREATE/Video Clips"),
              "/Volumes/Untitled/PS5/CREATE/Video Clips"]


def find_video(stem):
    for d in VIDEO_DIRS:
        p = os.path.join(d, stem + ".mp4")
        if os.path.exists(p):
            return p
    return None


def clip_id(fid):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", fid)


def clip_width(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0


def cut(video, t_end, out, length=4.0, width=640, loop=False):
    start = max(0.0, t_end - length + 0.8) if not loop else max(0.0, t_end)
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % start, "-t", "%.2f" % length, "-i", video,
           "-vf", "scale=%d:-2" % width, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    return subprocess.run(cmd, capture_output=True, text=True)


def findings_for(video):
    sys.path.insert(0, HERE)
    import server  # noqa: E402  — reuse the replay assembler
    r = server._replay(video)
    return r["findings"] if r else []


AUDIO = os.path.join(DATA, "app", "audio")


def cut_music(video, name, start, secs):
    os.makedirs(AUDIO, exist_ok=True)
    fade = "afade=t=in:st=0:d=1.5,afade=t=out:st=%.2f:d=1.5" % (secs - 1.5)
    outs = []
    for ext, codec in ((".m4a", ["-c:a", "aac", "-b:a", "160k"]), (".ogg", ["-c:a", "libvorbis", "-q:a", "5"])):
        out = os.path.join(AUDIO, name + ext)
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", "%.2f" % start, "-t", "%.2f" % secs, "-i", video, "-vn", "-af", fade] + codec + [out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        outs.append((out, r.returncode == 0, r.stderr[:160]))
    return outs


def main():
    args = sys.argv[1:]
    if "--music" in args:
        i = args.index("--music")
        name, start, secs = args[i + 1], float(args[i + 2]), float(args[i + 3])
        video = args[0] if i > 0 else "LongBatch1"
        src = find_video(video)
        if not src:
            print("no video file for", video); return 2
        for out, ok, err in cut_music(src, name, start, secs):
            print(os.path.basename(out), "ok" if ok else err)
        return 0
    video = args[0] if args and not args[0].startswith("--") else "LongBatch1"
    mx = int(args[args.index("--max") + 1]) if "--max" in args else 10 ** 9
    width = int(args[args.index("--width") + 1]) if "--width" in args else 1280
    redo = "--redo" in args
    os.makedirs(OUT, exist_ok=True)
    src = find_video(video)
    if not src:
        print("no video file for", video); return 2
    done = 0
    if "--menu" in args:
        out = os.path.join(OUT, "menu_%s.mp4" % video)
        if not os.path.exists(out):
            # seg 13 in LongBatch1 is Magik vs Storm with the 105-frame opening at 2231.8 s
            r = cut(src, 2226.0, out, length=8.0, width=960, loop=True)
            print("menu loop", "ok" if r.returncode == 0 else r.stderr[:200])
    for f in findings_for(video):
        if done >= mx:
            break
        out = os.path.join(OUT, clip_id(f["id"]) + ".mp4")
        if os.path.exists(out) and (not redo or clip_width(out) >= width):
            continue
        r = cut(src, float(f["t"]), out, width=width)
        done += 1
        print(f["id"], "ok" if r.returncode == 0 else r.stderr[:120])
    print("cut", done, "· have", len([x for x in os.listdir(OUT) if x.endswith(".mp4")]))


if __name__ == "__main__":
    main()
