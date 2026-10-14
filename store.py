import os
import shutil
import sqlite3
import threading
import time
import glob
from contextlib import closing

DB_PATH = os.path.join("data", "img23d.db")
_lock = threading.Lock()

ALLOWED = {
    "engine_used", "status", "stage", "error", "started", "finished",
    "vertices", "faces", "size_kb", "progress", "note",
}

# columns added after the first release; added to older databases on startup
MIGRATIONS = [
    ("kind", "TEXT DEFAULT 'single'"),
    ("image_count", "INTEGER DEFAULT 1"),
    ("progress", "INTEGER"),
    ("note", "TEXT"),
]


def _connect():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def init():
    os.makedirs("data", exist_ok=True)
    with _lock, closing(_connect()) as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY,
                original_name TEXT,
                engine TEXT,
                engine_used TEXT,
                status TEXT,
                stage TEXT,
                error TEXT,
                options TEXT,
                created REAL,
                started REAL,
                finished REAL,
                vertices INTEGER,
                faces INTEGER,
                size_kb INTEGER
            )"""
        )
        have = {r["name"] for r in c.execute("PRAGMA table_info(jobs)").fetchall()}
        for name, decl in MIGRATIONS:
            if name not in have:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {decl}")
        c.execute(
            "UPDATE jobs SET status='failed', stage='Failed', "
            "error='The server restarted before this job finished.' "
            "WHERE status IN ('queued','processing')"
        )
        c.commit()


def create_job(job_id, original_name, engine, options_json, kind="single", image_count=1):
    with _lock, closing(_connect()) as c:
        c.execute(
            "INSERT INTO jobs(id, original_name, engine, status, stage, options, created, kind, image_count) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, original_name, engine, "queued", "Waiting", options_json, time.time(), kind, image_count),
        )
        c.commit()


def update_job(job_id, **fields):
    bad = set(fields) - ALLOWED
    if bad:
        raise ValueError(f"Unknown fields: {bad}")
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock, closing(_connect()) as c:
        c.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*fields.values(), job_id))
        c.commit()


def get_job(job_id):
    with _lock, closing(_connect()) as c:
        return c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


def list_jobs(limit=60):
    with _lock, closing(_connect()) as c:
        return c.execute(
            "SELECT * FROM jobs ORDER BY created DESC LIMIT ?", (limit,)
        ).fetchall()


def queued_ahead(job_id):
    """Jobs that must finish before this one starts."""
    with _lock, closing(_connect()) as c:
        row = c.execute("SELECT created FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return 0
        n = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE "
            "(status='queued' AND created < ?) OR status='processing'",
            (row["created"],),
        ).fetchone()[0]
        return n


def delete_job(job_id):
    with _lock, closing(_connect()) as c:
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        c.commit()
    for p in glob.glob(os.path.join("outputs", f"{job_id}*")):
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
        except OSError:
            pass
