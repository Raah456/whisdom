"""
Frame sampling for the vision pipeline.

Kept apart from `damage` so the damage model stays pure image maths and can be
tested from PNGs on disk without ffmpeg present.
"""
import os
import shutil
import subprocess
import tempfile


def have_ffmpeg():
    return shutil.which("ffmpeg") is not None


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


class _Frames:
    """Sampled frames on disk, cleaned up on exit."""

    def __init__(self, dirpath, times):
        self.dir = dirpath
        self.times = times

    def __iter__(self):
        from PIL import Image
        for t, p in self.times:
            yield t, Image.open(p)

    def images(self):
        from PIL import Image
        return [Image.open(p) for _t, p in self.times]

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def sample(path, fps=None, count=None, region=None, start=0.0):
    """
    Extract frames to a temp dir.

    fps    : frames per second to sample (e.g. 2.0)
    count  : instead, spread roughly this many frames across the whole video
    region : ArcRegion to crop to — much faster than decoding full frames
    """
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg not found on PATH")
    if fps is None and count is None:
        raise ValueError("give either fps or count")
    if fps is None:
        d = duration(path) or 1.0
        fps = max(count / d, 1e-6)
    d = tempfile.mkdtemp(prefix="whisdom_frames_")
    vf = []
    if region is not None:
        vf.append("crop=%d:%d:%d:%d" % (region.w, region.h, region.x, region.y))
    vf.append("fps=%.6f" % fps)
    cmd = ["ffmpeg", "-v", "error"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", path, "-vf", ",".join(vf), "-y", os.path.join(d, "%06d.png")]
    subprocess.run(cmd, check=True)
    files = sorted(os.listdir(d))
    times = [(start + i / fps, os.path.join(d, f)) for i, f in enumerate(files)]
    return _Frames(d, times)
