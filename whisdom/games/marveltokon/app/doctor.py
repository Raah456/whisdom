"""What this machine can and cannot run.

The app's heavy jobs — reading a capture, reading a guide video — run as
subprocesses of whatever Python is serving the app. That Python is not the one
this code was written against: the dev box has ffmpeg, tesseract, numpy, OpenCV
and PIL; a fresh Mac has none of them. Without this file the first symptom of a
missing piece is a job that dies four minutes in with a traceback in a log file
nobody opens, and the feature looks broken rather than unavailable.

So: one list, checked in the SERVING interpreter, and every job consults it
before it starts and names the piece it needs instead of failing mid-way.

`brew` is not assumed — the install line for each piece says what to run, and
says `brew` only where that is genuinely the usual route on macOS.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.normpath(os.path.join(HERE, ".."))
APPDATA = os.path.join(PKG, "data", "app")


def _cmd(name):
    p = shutil.which(name)
    if not p:
        return None, None
    try:
        # --version first: tesseract answers -version with its usage screen.
        out = subprocess.run([name, "--version"], capture_output=True, text=True, timeout=6).stdout
        if not out or out.lower().startswith("usage"):
            out = subprocess.run([name, "-version"], capture_output=True, text=True, timeout=6).stdout
    except Exception:
        out = ""
    first = (out or "").strip().splitlines()[:1]
    return p, (first[0][:80] if first else "")


def _mod(name, attr="__version__"):
    try:
        m = __import__(name)
    except Exception as e:
        return None, type(e).__name__
    return getattr(m, attr, "installed"), None


# name, what it is for, how to get it
TOOLS = [
    ("ffmpeg", "cut frames and clips out of a capture", "brew install ffmpeg  (macOS) · apt install ffmpeg"),
    ("ffprobe", "read a capture's length and format — ships with ffmpeg", "brew install ffmpeg"),
    ("tesseract", "read the words in a guide video's captions", "brew install tesseract"),
]
MODULES = [
    ("numpy", "every frame is an array", "pip3 install numpy"),
    ("cv2", "template matching: the panel digits, the name plates, the captions", "pip3 install opencv-python"),
    ("PIL", "image cropping and clean-up for OCR", "pip3 install pillow"),
]
OPTIONAL = [
    ("whisper", "speech to text for commentary — not required; transcripts can be pasted", "pip3 install openai-whisper  ·  or brew install whisper-cpp"),
]

# which pieces each job actually needs
JOBS = {
    "replay": ["ffmpeg", "numpy", "cv2"],
    "clips": ["ffmpeg"],
    "source_frames": ["ffmpeg"],
    "source_ocr": ["tesseract", "PIL"],
    "source_audio": ["ffmpeg"],
    "transcribe": ["whisper"],
}
JOB_NAMES = {
    "replay": "Drop a match — reading a capture",
    "clips": "cutting the receipt clips",
    "source_frames": "reading frames out of a guide video",
    "source_ocr": "reading the words on those frames",
    "source_audio": "pulling a guide's audio",
    "transcribe": "turning that audio into text",
}


def check():
    rows = []
    for name, why, how in TOOLS:
        path, ver = _cmd(name)
        rows.append({"name": name, "kind": "command", "ok": bool(path), "why": why,
                     "detail": ver or path or "not on PATH", "install": how, "optional": False})
    for name, why, how in MODULES:
        ver, err = _mod(name)
        rows.append({"name": name, "kind": "python", "ok": ver is not None, "why": why,
                     "detail": str(ver) if ver else err or "not importable", "install": how, "optional": False})
    for name, why, how in OPTIONAL:
        ver, err = _mod(name)
        ok = ver is not None or shutil.which("whisper") or shutil.which("whisper-cli") or shutil.which("whisper-cpp")
        rows.append({"name": name, "kind": "optional", "ok": bool(ok), "why": why,
                     "detail": str(ver) if ver else "not installed", "install": how, "optional": True})
    have = {r["name"] for r in rows if r["ok"]}
    jobs = []
    for key, needs in JOBS.items():
        miss = [n for n in needs if n not in have]
        jobs.append({"job": key, "name": JOB_NAMES[key], "ok": not miss, "missing": miss,
                     "needs": needs})
    du = None
    try:
        st = os.statvfs(APPDATA if os.path.isdir(APPDATA) else PKG)
        du = {"free_gb": round(st.f_bavail * st.f_frsize / 1e9, 1),
              "total_gb": round(st.f_blocks * st.f_frsize / 1e9, 1)}
    except Exception:
        pass
    return {
        "python": {"version": sys.version.split()[0], "executable": sys.executable,
                   "note": "this is the interpreter the app's jobs run in — installing into a different one will not help"},
        "tools": rows, "jobs": jobs, "disk": du,
        "data_dir": APPDATA, "data_exists": os.path.isdir(APPDATA),
        "missing": sorted({n for j in jobs for n in j["missing"]}),
        "all_ok": all(j["ok"] for j in jobs if j["job"] != "transcribe"),
    }


def gate(job):
    """None if the job can run, else a sentence naming what is missing and how to get it."""
    needs = JOBS.get(job) or []
    rows = {r["name"]: r for r in check()["tools"]}
    miss = [n for n in needs if not (rows.get(n) or {}).get("ok")]
    if not miss:
        return None
    how = "; ".join((rows.get(n) or {}).get("install", "") for n in miss)
    return ("%s needs %s, and %s not on this machine. %s — then reopen this screen. "
            "(Options → Doctor lists everything.)"
            % (JOB_NAMES.get(job, job), " and ".join(miss),
               "it is" if len(miss) == 1 else "they are", how))


if __name__ == "__main__":
    import json
    print(json.dumps(check(), indent=1))
