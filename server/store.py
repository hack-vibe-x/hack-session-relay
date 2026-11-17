"""Index of the stored session files in SQLite, so reads never walk the folders. Standard library only.

The files under users/ stay the record; the index (DATA_DIR/index.db) is derived from them and can be deleted at
any time: the server rebuilds it at the next start. Every upload updates its row as it is written, and a start
compares the index with the folders, so a row lost to a crash between the file and the index comes back.

One row per slice (one session's lines for one local date), the same unit as one .jsonl.gz file.
"""
import json
import os
import re
import sqlite3
import threading

SCHEMA = 1  # Raise when the table changes: the index is then dropped and rebuilt from the files.
DATE = re.compile(r"^\d{4}-\d\d-\d\d$")
CREATE = """
CREATE TABLE slices (
  user_id TEXT NOT NULL, date TEXT NOT NULL, tool TEXT NOT NULL, session_id TEXT NOT NULL,
  gz_bytes INTEGER NOT NULL, bytes INTEGER, lines INTEGER, first TEXT, last TEXT, cwd TEXT, uploaded_at TEXT,
  meta TEXT NOT NULL, mtime REAL NOT NULL,
  PRIMARY KEY (user_id, date, tool, session_id)
) WITHOUT ROWID;
CREATE INDEX slices_session ON slices (user_id, tool, session_id);
"""


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class Index:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        if self.db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA:
            self.db.execute("DROP TABLE IF EXISTS slices")
            self.db.executescript(CREATE)
            self.db.execute("PRAGMA user_version=%d" % SCHEMA)

    # ----- writes -----

    def put(self, uid, day, tool, sid, meta, gz_bytes, mtime):
        row = (uid, day, tool, sid, gz_bytes, _int(meta.get("bytes")), _int(meta.get("lines")), meta.get("first"),
               meta.get("last"), meta.get("cwd"), meta.get("uploaded_at"), json.dumps(meta), mtime)
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO slices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", row)

    def reconcile(self, users_dir):
        """Make the index match the folders. Reads a meta file only for slices that are new or changed."""
        on_disk = {}
        try:
            uids = os.listdir(users_dir)
        except FileNotFoundError:
            uids = []
        for uid in uids:
            base = os.path.join(users_dir, uid)
            if not os.path.isdir(base):
                continue
            for day in os.listdir(base):
                if not DATE.match(day):
                    continue
                for name in os.listdir(os.path.join(base, day)):
                    if not name.endswith(".jsonl.gz") or "_" not in name:
                        continue
                    tool, sid = name[:-len(".jsonl.gz")].split("_", 1)
                    on_disk[(uid, day, tool, sid)] = os.path.join(base, day, name)
        with self.lock:
            indexed = {tuple(r[:4]): r[4] for r in self.db.execute(
                "SELECT user_id, date, tool, session_id, mtime FROM slices")}
        changed = 0
        for key in indexed.keys() - on_disk.keys():
            with self.lock:
                self.db.execute("DELETE FROM slices WHERE user_id=? AND date=? AND tool=? AND session_id=?", key)
            changed += 1
        for key, path in on_disk.items():
            try:
                stat = os.stat(path)
            except FileNotFoundError:
                continue
            if indexed.get(key) == stat.st_mtime:
                continue
            try:
                with open(path[:-len(".jsonl.gz")] + ".meta.json", encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                meta = {}
            meta.setdefault("tool", key[2])
            meta.setdefault("session_id", key[3])
            self.put(*key, meta, stat.st_size, stat.st_mtime)
            changed += 1
        return changed

    # ----- reads -----

    def days(self, uid=None):
        """{user id: [{date, sessions, bytes, tools}, ...] newest first}, for one user or all of them."""
        sql = "SELECT user_id, date, tool, COUNT(*), SUM(gz_bytes) FROM slices"
        args = ()
        if uid:
            sql, args = sql + " WHERE user_id=?", (uid,)
        sql += " GROUP BY user_id, date, tool ORDER BY user_id, date DESC"
        out = {}
        with self.lock:
            rows = self.db.execute(sql, args).fetchall()
        for user_id, day, tool, count, size in rows:
            days = out.setdefault(user_id, [])
            if not days or days[-1]["date"] != day:
                days.append({"date": day, "sessions": 0, "bytes": 0, "tools": {}})
            days[-1]["sessions"] += count
            days[-1]["bytes"] += size
            days[-1]["tools"][tool] = count
        return out

    def sessions(self, uid, day):
        """The slices of one date, each with "dates": every date the same session appears on."""
        with self.lock:
            rows = self.db.execute(
                "SELECT s.meta, s.gz_bytes, (SELECT group_concat(o.date) FROM (SELECT date FROM slices o "
                "WHERE o.user_id=s.user_id AND o.tool=s.tool AND o.session_id=s.session_id ORDER BY date) o) "
                "FROM slices s WHERE s.user_id=? AND s.date=?", (uid, day)).fetchall()
        out = []
        for meta, gz_bytes, dates in rows:
            meta = json.loads(meta)
            meta.setdefault("gz_bytes", gz_bytes)
            meta["dates"] = dates.split(",")
            out.append(meta)
        out.sort(key=lambda m: m.get("first") or "")
        return out
