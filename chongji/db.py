"""SQLite:存每次照护评估的物种、体重、阶段、症状分级与明细。"""

from __future__ import annotations

import json
import os
import sqlite3
import threading

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chongji.db")


class Database:
    def __init__(self, path=None):
        self.path = path or os.environ.get("CHONGJI_DB") or DEFAULT_DB_PATH
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    species TEXT, weight REAL, stage TEXT, triage TEXT,
                    grams INTEGER, detail TEXT,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            self.conn.commit()

    def save(self, r):
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO records (species, weight, stage, triage, grams, detail) "
                "VALUES (?,?,?,?,?,?)",
                (r["species"]["name"] if r["species"] else None, r["weight"], r["stage"]["name"],
                 r["triage"]["level"], (r["plan"] or {}).get("grams"), json.dumps(r, ensure_ascii=False)),
            )
            self.conn.commit()
            return int(cur.lastrowid)

    def latest(self, limit=10):
        with self._lock:
            rows = self.conn.execute(
                "SELECT id, species, weight, stage, triage, grams, created_at "
                "FROM records ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
