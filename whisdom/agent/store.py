"""
Local persistence.

Match documents are JSON on disk (source of truth, schema-shaped, inspectable).
A SQLite index sits alongside for querying; it is fully rebuildable from the JSON,
so it is treated as a cache, never as authoritative.
"""
import os, json, sqlite3, time, threading

class Store:
    def __init__(self, root, index_dir=None):
        """
        Match documents (JSON) are the source of truth and live under `root`.

        The SQLite index is a disposable cache and may live elsewhere via
        `index_dir`. That matters because SQLite needs real file locking: if a
        user keeps their data on OneDrive / Dropbox / iCloud / a network share,
        the documents are fine there but the index must be on local disk.
        Rebuild at any time with `reindex`.
        """
        self.root=os.path.abspath(root)
        self.matches=os.path.join(self.root,"matches")
        os.makedirs(self.matches, exist_ok=True)
        idx = os.path.abspath(index_dir) if index_dir else self.root
        os.makedirs(idx, exist_ok=True)
        self.dbpath=os.path.join(idx,"index.sqlite")
        self._local=threading.local()
        self._schema()

    @property
    def db(self):
        """
        One connection per thread.

        SQLite refuses to let a connection cross threads, and the local app
        serves each request on its own thread. Connections are cheap and the
        index is a local file, so a thread-local connection is simpler and safer
        than sharing one behind a lock.
        """
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.dbpath)
            c.row_factory = sqlite3.Row
            self._local.conn = c
        return c

    def _schema(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS matches(
          match_id TEXT PRIMARY KEY, source_file TEXT, game TEXT, patch TEXT,
          fps INTEGER, duration_frames INTEGER, ingested_at REAL,
          analyzer_version TEXT, schema_version TEXT, has_kos INTEGER,
          has_video INTEGER DEFAULT 0, level_name TEXT);
        CREATE TABLE IF NOT EXISTS players(
          match_id TEXT, slot INTEGER, display_name TEXT, character TEXT,
          character_id INTEGER, PRIMARY KEY(match_id,slot));
        CREATE TABLE IF NOT EXISTS metrics(
          match_id TEXT, slot INTEGER, key TEXT, value REAL,
          PRIMARY KEY(match_id,slot,key));
        CREATE TABLE IF NOT EXISTS moments(
          id TEXT PRIMARY KEY, match_id TEXT, slot INTEGER, frame INTEGER,
          kind TEXT, severity INTEGER, title TEXT);
        CREATE INDEX IF NOT EXISTS ix_players_name ON players(display_name);
        CREATE INDEX IF NOT EXISTS ix_metrics_key  ON metrics(key);
        CREATE INDEX IF NOT EXISTS ix_moments_kind ON moments(kind);
        """)
        # The index is a cache, so widening it is allowed to be lossy: older
        # databases simply gain empty columns until the next reindex.
        have = {r["name"] for r in self.db.execute("PRAGMA table_info(matches)")}
        for col, decl in (("has_video", "INTEGER DEFAULT 0"), ("level_name", "TEXT")):
            if col not in have:
                self.db.execute("ALTER TABLE matches ADD COLUMN %s %s" % (col, decl))
        self.db.commit()

    # ---- idempotency -------------------------------------------------
    def has(self, match_id):
        return self.db.execute("SELECT 1 FROM matches WHERE match_id=?", (match_id,)).fetchone() is not None

    def path_for(self, match_id):
        return os.path.join(self.matches, match_id + ".json")

    # ---- write -------------------------------------------------------
    def save(self, doc, metrics=None):
        mid=doc["match"]["id"]
        with open(self.path_for(mid),"w") as f:
            json.dump(doc,f)
        m=doc["match"]
        self.db.execute("""INSERT OR REPLACE INTO matches
               (match_id,source_file,game,patch,fps,duration_frames,ingested_at,
                analyzer_version,schema_version,has_kos,has_video,level_name)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (mid, m.get("source_file"), m.get("game"), m.get("patch"), m.get("fps"),
             m.get("duration_frames"), time.time(), doc.get("analyzer_version"),
             doc.get("schema_version"), 1 if doc["observations"].get("kos") else 0,
             1 if doc["observations"].get("damage") else 0, m.get("level_name")))
        self.db.execute("DELETE FROM players WHERE match_id=?", (mid,))
        for p in doc["players"]:
            leg=p.get("character") or p.get("legend") or {}
            self.db.execute("INSERT OR REPLACE INTO players VALUES(?,?,?,?,?)",
                (mid, p["slot"], p.get("display_name"), leg.get("name"), leg.get("id")))
        self.db.execute("DELETE FROM moments WHERE match_id=?", (mid,))
        for mo in doc["analysis"]["moments"]:
            self.db.execute("INSERT OR REPLACE INTO moments VALUES(?,?,?,?,?,?,?)",
                (mo["id"], mid, mo.get("slot"), mo["frame"], mo["kind"], mo["severity"], mo.get("title")))
        if metrics:
            self.db.execute("DELETE FROM metrics WHERE match_id=?", (mid,))
            for slot,vals in metrics.items():
                for k,v in (vals or {}).items():
                    if isinstance(v,(int,float)):
                        self.db.execute("INSERT OR REPLACE INTO metrics VALUES(?,?,?,?)",(mid,int(slot),k,float(v)))
        self.db.commit()
        return mid

    # ---- read --------------------------------------------------------
    def load(self, match_id):
        p=self.path_for(match_id)
        return json.load(open(p)) if os.path.exists(p) else None

    def count(self):
        return self.db.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]

    def players_seen(self, limit=20):
        return self.db.execute("""SELECT display_name, COUNT(*) n FROM players
                                  WHERE display_name IS NOT NULL
                                  GROUP BY display_name ORDER BY n DESC LIMIT ?""",(limit,)).fetchall()

    def metric_series(self, name, key):
        return self.db.execute("""SELECT m.patch, mt.value FROM metrics mt
              JOIN players p ON p.match_id=mt.match_id AND p.slot=mt.slot
              JOIN matches m ON m.match_id=mt.match_id
              WHERE p.display_name=? AND mt.key=? ORDER BY m.ingested_at""",(name,key)).fetchall()

    def list_matches(self, player=None, has_video=None, patch=None, q=None,
                     limit=200, offset=0):
        """Match rows for the browser, newest first."""
        sql = ["""SELECT m.match_id, m.patch, m.level_name, m.duration_frames, m.fps,
                         m.has_video, m.has_kos, m.ingested_at,
                         GROUP_CONCAT(p.display_name, ' vs ') AS who
                  FROM matches m LEFT JOIN players p ON p.match_id = m.match_id"""]
        where, args = [], []
        if player:
            where.append("""m.match_id IN (SELECT match_id FROM players
                                           WHERE display_name = ?)""")
            args.append(player)
        if has_video is not None:
            where.append("m.has_video = ?"); args.append(1 if has_video else 0)
        if patch:
            where.append("m.patch = ?"); args.append(patch)
        if q:
            where.append("(m.level_name LIKE ? OR m.source_file LIKE ?)")
            args += ["%" + q + "%", "%" + q + "%"]
        if where:
            sql.append("WHERE " + " AND ".join(where))
        sql.append("GROUP BY m.match_id ORDER BY m.ingested_at DESC LIMIT ? OFFSET ?")
        args += [limit, offset]
        return self.db.execute(" ".join(sql), args).fetchall()

    def facets(self):
        """Counts the browser needs to show what is available."""
        one = lambda q: self.db.execute(q).fetchone()[0]
        return dict(
            total=one("SELECT COUNT(*) FROM matches"),
            with_video=one("SELECT COUNT(*) FROM matches WHERE has_video=1"),
            with_kos=one("SELECT COUNT(*) FROM matches WHERE has_kos=1"),
            patches=[r[0] for r in self.db.execute(
                "SELECT DISTINCT patch FROM matches WHERE patch IS NOT NULL ORDER BY patch DESC")],
        )

    def rebuild_index(self):
        """The index is a cache. Drop it and re-derive from the JSON documents."""
        self.db.executescript("DROP TABLE IF EXISTS matches; DROP TABLE IF EXISTS players;"
                              "DROP TABLE IF EXISTS metrics; DROP TABLE IF EXISTS moments;")
        self._schema()
        n=0
        for fn in os.listdir(self.matches):
            if fn.endswith(".json"):
                self.save(json.load(open(os.path.join(self.matches,fn)))); n+=1
        return n
