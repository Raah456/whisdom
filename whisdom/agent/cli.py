"""
whisdom command line.

    whisdom ingest            process every replay found (safe to re-run)
    fightlab watch             keep running; pick up new matches automatically
    whisdom status            what's in the store
    whisdom report <target>   HTML report for a match id, or a player profile
    whisdom where             show detected paths and diagnose problems
"""
import os, sys, json, argparse, time


from whisdom.agent.paths import (find_replay_dir, replay_dir_help, default_data_dir,
                   sqlite_usable, sqlite_help)

CONFIG_NAME = "config.json"

def load_config(data_dir):
    p = os.path.join(data_dir, CONFIG_NAME)
    if os.path.exists(p):
        try: return json.load(open(p))
        except Exception: pass
    return {}

def save_config(data_dir, cfg):
    os.makedirs(data_dir, exist_ok=True)
    json.dump(cfg, open(os.path.join(data_dir, CONFIG_NAME), "w"), indent=1)

def game_module(name):
    """Resolve a game adapter from the registry. Adding a game changes nothing here."""
    from whisdom.games.base import get
    a = get(name)
    return a.load_match, a.action_model, a.categories

def resolve_replays(arg, cfg, adapter):
    path, how = find_replay_dir(arg or cfg.get("replay_dir"), adapter)
    if not path:
        raise SystemExit(replay_dir_help(adapter))
    return path, how

def open_store(data_dir, index_dir=None):
    target = index_dir or data_dir
    ok, err = sqlite_usable(target)
    if not ok:
        msg = sqlite_help(target, err)
        if not index_dir:
            msg += ("\n\nOr keep the documents where they are and put only the index\n"
                    "on local disk:\n   whisdom --data \"%s\" --index <local-path> ingest" % data_dir)
        raise SystemExit(msg)
    from whisdom.agent.store import Store
    return Store(data_dir, index_dir=index_dir)

def main(argv=None):
    ap = argparse.ArgumentParser(prog="whisdom", description="Replay analysis for platform fighters.")
    ap.add_argument("--game", default="brawlhalla", help="which game adapter to use")
    ap.add_argument("--data", default=None, help="where to keep the store (default: per-OS app data)")
    ap.add_argument("--index", default=None,
                    help="where to keep the SQLite index (default: alongside --data). "
                         "Use local disk if --data is on a cloud-synced or network folder.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="process a folder of replays once")
    p.add_argument("folder", nargs="?"); p.add_argument("--limit", type=int)
    p = sub.add_parser("watch", help="watch for new replays and process them")
    p.add_argument("folder", nargs="?"); p.add_argument("--interval", type=int, default=10)
    sub.add_parser("status", help="summarise the store")
    p = sub.add_parser("report", help="write an HTML report")
    p.add_argument("target"); p.add_argument("--out")
    p = sub.add_parser("clips", help="cut annotated clips from a recording of a match")
    p.add_argument("match_id"); p.add_argument("video")
    p.add_argument("--offset", type=int, default=0,
                   help="ms into the video where the match starts")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--out")
    p = sub.add_parser("damage", help="read damage off a recording and attach it to a match")
    p.add_argument("match_id"); p.add_argument("video")
    p.add_argument("--fps", type=float, default=2.0, help="how often to sample damage")
    p.add_argument("--dry-run", action="store_true", help="report but do not save")
    p = sub.add_parser("review", help="review the exchanges that killed you")
    p.add_argument("match_id"); p.add_argument("--player")
    p.add_argument("--window", type=float, default=3.0,
                   help="seconds before each death to treat as the exchange")
    p = sub.add_parser("demo", help="clips of every death, captioned with the verdict")
    p.add_argument("match_id"); p.add_argument("video"); p.add_argument("--out")
    p = sub.add_parser("app", help="open the local app in your browser")
    p.add_argument("--port", type=int, default=8756)
    p.add_argument("--no-open", action="store_true", help="do not launch a browser")
    sub.add_parser("reindex", help="rebuild the index from stored documents")
    sub.add_parser("where", help="show detected paths and diagnose problems")
    a = ap.parse_args(argv)

    data_dir = a.data or default_data_dir()
    cfg = load_config(data_dir)

    if a.cmd == "where":
        from whisdom.games.base import available, get as _g
        adapter = _g(a.game)
        print("game          : %s   (available: %s)" % (adapter.display_name, ", ".join(available())))
        print("data dir      : %s" % data_dir)
        idx = a.index or data_dir
        ok, err = sqlite_usable(idx)
        print("index dir     : %s" % idx)
        print("database      : %s" % ("ok" if ok else "UNUSABLE — %s" % err))
        path, how = find_replay_dir(cfg.get("replay_dir"), adapter)
        if path:
            import glob as _g
            n = len(_g.glob(os.path.join(path, "**", "*"+adapter.replay_ext), recursive=True))
            print("replay folder : %s  (%s, %d replays)" % (path, how, n))
        else:
            print("replay folder : NOT FOUND\n"); print(replay_dir_help(adapter))
        return

    from whisdom.games.base import get as _get_adapter
    adapter = _get_adapter(a.game)
    store = open_store(data_dir, a.index)
    loader, model, cats = adapter.load_match, adapter.action_model, adapter.categories

    if a.cmd == "ingest":
        folder, how = resolve_replays(a.folder, cfg, adapter)
        cfg["replay_dir"] = folder; save_config(data_dir, cfg)
        print("replays: %s (%s)\nstore  : %s\n" % (folder, how, data_dir))
        from whisdom.agent.pipeline import ingest_folder
        t = time.time()
        st = ingest_folder(folder, store, loader, model, cats,
                           pattern=adapter.replay_ext, progress=200, limit=a.limit)
        print("\n%d new, %d already known, %d failed  (%.0fs)"
              % (st["ok"], st["skipped"], st["failed"], time.time() - t))
        for e in st["errors"][:5]: print("   failed:", e)
        if st["ok"] or st["skipped"]:
            print("\nnext: whisdom report <a player name>")
    elif a.cmd == "watch":
        folder, how = resolve_replays(a.folder, cfg, adapter)
        cfg["replay_dir"] = folder; save_config(data_dir, cfg)
        from whisdom.agent.pipeline import ingest_file
        from whisdom.agent.watch import watch
        print("watching %s every %ds — Ctrl-C to stop" % (folder, a.interval))
        def on_new(p):
            st, info = ingest_file(p, store, loader, model, cats)
            print("  [%s] %s" % (st, os.path.basename(p)), flush=True)
        try: watch(folder, on_new, interval=a.interval, pattern=adapter.replay_ext)
        except KeyboardInterrupt: print("\nstopped")
    elif a.cmd == "status":
        print("store   : %s" % data_dir)
        print("matches : %d" % store.count())
        rows = store.players_seen(10)
        if rows:
            print("players seen:")
            for r in rows: print("   %-22s %d" % (r["display_name"], r["n"]))
        else:
            print("nothing ingested yet — run: whisdom ingest")
    elif a.cmd == "report":
        from whisdom.agent.report import match_report, profile_report
        out = a.out
        if store.load(a.target):
            out = out or os.path.join(data_dir, "report_%s.html" % a.target)
            print("wrote", match_report(store, a.target, out, adapter))
        else:
            out = out or os.path.join(data_dir, "profile_%s.html" % a.target.replace(" ", "_"))
            try: print("wrote", profile_report(store, a.target, out, adapter))
            except ValueError:
                raise SystemExit("no matches for %r. Try: whisdom status" % a.target)
    elif a.cmd == "clips":
        from whisdom.agent.clips import make_clips
        outdir, made = make_clips(store, a.match_id, a.video, offset_ms=a.offset,
                                  outdir=a.out, limit=a.limit)
        ok = sum(1 for c in made if c["file"])
        print("wrote %d clips to %s" % (ok, outdir))
        print("open %s to review and check the sync" % os.path.join(outdir, "index.html"))
        for c in made:
            if not c["file"]: print("   failed: %s — %s" % (c["moment"].get("title"), (c["error"] or "")[:80]))
    elif a.cmd == "damage":
        from whisdom.agent import vision_link as vl
        doc = store.load(a.match_id)
        if not doc:
            raise SystemExit("no match %s in the store" % a.match_id)
        names = {p["slot"]: (p.get("display_name") or "slot %d" % p["slot"])
                 for p in doc["players"]}
        try:
            res = vl.analyse(doc, a.video, sample_fps=a.fps,
                             progress=lambda m: print("   %s..." % m))
        except RuntimeError as e:
            raise SystemExit("\n%s" % e)
        print("\nvideo starts %+.2fs relative to the match" % res["offset"])
        print("(derived from the deaths — no manual sync needed)\n")
        for ai, slot in sorted(res["mapping"].items(), key=lambda kv: kv[0]):
            m, miss, sp = res["check"][slot]
            side = "left" if ai == 0 else "right" if ai == 1 else "arc %d" % ai
            print("   %-5s HUD = %-18s deaths %d/%d confirmed%s"
                  % (side, names.get(slot, "?"), len(m), len(m) + len(miss),
                     "" if not sp else "   %d unexplained reset(s)" % len(sp)))
        bad = sum(len(v[1]) + len(v[2]) for v in res["check"].values())
        if bad:
            print("\nwarning: the recording and the replay do not fully agree — "
                  "check they are the same match before trusting the damage.")
        if a.dry_run:
            print("\ndry run; nothing saved")
        else:
            vl.attach(doc, res, a.video)
            store.save(doc)
            n = len(doc["observations"]["damage"])
            print("\nattached %d damage readings to %s" % (n, a.match_id))
            print("next: whisdom report %s" % a.match_id)
    elif a.cmd == "review":
        from whisdom.agent.review import review_match
        doc = store.load(a.match_id)
        if not doc:
            raise SystemExit("no match %s in the store" % a.match_id)
        r = review_match(doc, a.player, a.window)
        if not r or not r["deaths"]:
            raise SystemExit("nothing to review: this match has no KOs, or no "
                             "inputs were recorded before them")
        has_dmg = bool(doc.get("observations", {}).get("damage"))
        print("reviewing %s vs %s\n" % (r["player"], r["opponent"]))
        if not has_dmg:
            print("NOTE: no damage track — pair a recording with `whisdom damage` "
                  "first, or these are judged at assumed 50%% damage.\n")
        t = r["tendency"]
        lbl = {k: l for k, l in __import__("whisdom.games.brawlhalla.payoffs",
                                           fromlist=["x"]).ATK_OPTIONS}
        print("%s tends to (from %d observed presses):" % (r["opponent"], r["tendency_n"]))
        for k, v in sorted(t.items(), key=lambda kv: -kv[1]):
            print("   %-22s %3.0f%%" % (lbl.get(k, k), 100 * v))
        if r["tendency_ambiguous"] > 0.2:
            print("   (%.0f%% of these are ambiguous without position data)"
                  % (100 * r["tendency_ambiguous"]))
        print()
        for d in r["deaths"]:
            dm = ("%.0f%%" % (100 * d["my_damage"])) if d["my_damage"] is not None else "unknown"
            td = ("%.0f%%" % (100 * d["their_damage"])) if d["their_damage"] is not None else "unknown"
            print("death at %5.1fs   you were at %s, they were at %s" % (d["seconds"], dm, td))
            print("   you chose  : %-20s (%s at %.1fs)"
                  % (d["chose"], "+".join(d["inputs"]), d["at"]))
            if d["my_ev"] is not None:
                print("   worth      : %+.2f" % d["my_ev"])
            if d["gap"] and d["gap"] > 0.02:
                print("   better     : %-20s %+.2f   (%+.2f better)"
                      % (d["best"], d["best_ev"], d["gap"]))
                print("   because    : %s" % d["why_best"])
            else:
                print("   verdict    : best available option here")
            if d["confidence"] < 1.0:
                print("   caution    : frame data for this option is unverified")
            print()
    elif a.cmd == "demo":
        from whisdom.agent.demo import build
        outdir, made, page, rev = build(store, a.match_id, a.video, outdir=a.out,
                                        progress=lambda m: print("   %s..." % m))
        ok = sum(1 for c in made if c["file"])
        print("\n%d clips for %s" % (ok, rev["player"]))
        for c in made:
            d = c["d"]
            print("   %5.1fs  %-20s %+.2f%s" % (
                d["seconds"], d["chose"], d["my_ev"] or 0.0,
                "   -> %s %+.2f" % (d["best"], d["best_ev"])
                if d["gap"] and d["gap"] > 0.02 else ""))
        print("\nopen %s" % page)
    elif a.cmd == "app":
        from whisdom.app.server import serve
        httpd, url = serve(store, port=a.port, open_browser=not a.no_open)
        print("Whisdom is running at %s" % url)
        print("store: %s   (%d matches)" % (data_dir, store.count()))
        f = store.facets()
        if f["total"] and not f["with_video"]:
            print("note : no match has a recording paired yet, so the review panel")
            print("       will judge at an assumed 50%. Pair one with:")
            print("       whisdom demo <match_id> <recording.mp4>")
        print("everything stays on this machine. Ctrl-C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    elif a.cmd == "reindex":
        print("rebuilt index from %d documents" % store.rebuild_index())

if __name__ == "__main__":
    main()
