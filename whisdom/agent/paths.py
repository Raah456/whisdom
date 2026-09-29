"""
Locating a game's replay folder, and choosing a safe place for our data.

Candidate locations come from the GAME ADAPTER, not from here — different games
store replays in different places, and a single game can use more than one layout
across platforms. Rather than guess once and fail cryptically,
check every plausible candidate, and if none match, search a couple of likely
roots before giving up with a message that tells the user what to do.
"""
import os, sys, glob, sqlite3, tempfile

def _home(*parts): return os.path.join(os.path.expanduser("~"), *parts)

def _platform_key():
    if sys.platform.startswith("win"): return "win"
    if sys.platform == "darwin": return "darwin"
    return "linux"

def replay_candidates(adapter=None):
    """
    Plausible replay directories for a game, most likely first.
    Supplied by the game adapter — nothing here knows which game it is.
    """
    if adapter is None: return []
    return list(adapter.replay_paths.get(_platform_key(), []))

def find_replay_dir(explicit=None, adapter=None):
    """Return (path, how_found) or (None, None)."""
    ext = adapter.replay_ext if adapter else ".replay"
    if explicit:
        return (explicit, "given") if os.path.isdir(explicit) else (None, None)
    for p in replay_candidates(adapter):
        if os.path.isdir(p) and glob.glob(os.path.join(p, "**", "*"+ext), recursive=True):
            return p, "known location"
    for p in replay_candidates():
        if os.path.isdir(p):
            return p, "known location (empty)"
    # last resort: a shallow search of likely roots
    roots = [_home("Documents"), _home("Library", "Application Support"), _home()]
    for root in roots:
        if not os.path.isdir(root): continue
        for depth in ("*/*"+ext, "*/*/*"+ext, "*/*/*/*"+ext):
            hits = glob.glob(os.path.join(root, depth))
            if hits:
                return os.path.dirname(hits[0]), "found by search"
    return None, None

def replay_dir_help(adapter=None):
    game = adapter.display_name if adapter else "the game"
    lines = ["Could not find your %s replay folder." % game, "", "Looked in:"]
    for p in replay_candidates(adapter):
        lines.append("   %s %s" % ("[found]" if os.path.isdir(p) else "       ", p))
    lines += ["",
              (adapter.replay_help if adapter else
               "Check the game's own replay browser for the folder location."),
              "Then pass it explicitly:", "   whisdom ingest \"/path/to/replays\""]
    return "\n".join(lines)

# ---------------------------------------------------------------- data dir
def default_data_dir():
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or _home("AppData", "Local")
        return os.path.join(base, "whisdom")
    if sys.platform == "darwin":
        return _home("Library", "Application Support", "whisdom")
    return os.environ.get("XDG_DATA_HOME") or _home(".local", "share", "whisdom")

def sqlite_usable(path):
    """
    SQLite needs real file locking. Network shares, some FUSE mounts and a few
    cloud-sync folders don't provide it and fail with a bare 'disk I/O error'.
    Test before we get there so the message can be useful.
    """
    os.makedirs(path, exist_ok=True)
    probe = os.path.join(path, ".whisdom_probe.sqlite")
    try:
        db = sqlite3.connect(probe)
        db.execute("CREATE TABLE IF NOT EXISTS t(x INTEGER)")
        db.execute("INSERT INTO t VALUES (1)")
        db.commit(); db.close()
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        try: os.remove(probe)
        except OSError: pass

def sqlite_help(path, err):
    return ("\n".join([
        "Cannot use a database in:", "   %s" % path, "",
        "SQLite reported: %s" % err, "",
        "This usually means the folder is on a network share or a cloud-sync",
        "folder (OneDrive, Dropbox, iCloud) that doesn't support file locking.", "",
        "Point --data at local disk instead, for example:",
        "   whisdom --data \"%s\" status" % os.path.join(tempfile.gettempdir(), "whisdom")]))
