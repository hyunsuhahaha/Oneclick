"""SQLite 저장소: 릴리스, 대상별 배포, 로그, 로컬 포트 할당."""
import sqlite3
import threading
import time
import uuid

from . import config

# 배포 상태
QUEUED, BUILDING, DEPLOYING, LIVE, FAILED, SUPERSEDED = (
    "queued", "building", "deploying", "live", "failed", "superseded")
TERMINAL = {LIVE, FAILED, SUPERSEDED}

SCHEMA = """
CREATE TABLE IF NOT EXISTS releases (
    id TEXT PRIMARY KEY, app TEXT, source TEXT, image TEXT,
    kind TEXT, created_at REAL
);
CREATE TABLE IF NOT EXISTS deployments (
    id TEXT PRIMARY KEY, release_id TEXT, app TEXT, target TEXT, image TEXT,
    status TEXT, url TEXT, error TEXT, created_at REAL, finished_at REAL
);
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, release_id TEXT, scope TEXT,
    ts REAL, line TEXT
);
CREATE TABLE IF NOT EXISTS local_ports (app TEXT PRIMARY KEY, port INTEGER UNIQUE);
CREATE INDEX IF NOT EXISTS idx_logs_release ON logs(release_id, id);
CREATE INDEX IF NOT EXISTS idx_dep_app ON deployments(app, target, created_at);
"""

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        config.ensure_dirs()
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def _exec(sql: str, args: tuple = ()) -> None:
    with _lock:
        db().execute(sql, args)
        db().commit()


def _query(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in db().execute(sql, args).fetchall()]


def new_id() -> str:
    return time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


# ---- 릴리스 / 배포 ----

def create_release(app: str, source: str, kind: str = "deploy", image: str = "") -> str:
    rid = new_id()
    _exec("INSERT INTO releases VALUES (?,?,?,?,?,?)",
          (rid, app, source, image, kind, time.time()))
    return rid


def set_release_image(rid: str, image: str) -> None:
    _exec("UPDATE releases SET image=? WHERE id=?", (image, rid))


def create_deployment(rid: str, app: str, target: str) -> str:
    did = uuid.uuid4().hex[:12]
    _exec("INSERT INTO deployments VALUES (?,?,?,?,?,?,?,?,?,?)",
          (did, rid, app, target, "", QUEUED, "", "", time.time(), None))
    return did


def update_deployment(did: str, **fields) -> None:
    if fields.get("status") in TERMINAL:
        fields.setdefault("finished_at", time.time())
    cols = ", ".join(f"{k}=?" for k in fields)
    _exec(f"UPDATE deployments SET {cols} WHERE id=?", (*fields.values(), did))


def deployments_of(rid: str) -> list[dict]:
    return _query("SELECT * FROM deployments WHERE release_id=? ORDER BY target", (rid,))


def live_deployment(app: str, target: str) -> dict | None:
    rows = _query("SELECT * FROM deployments WHERE app=? AND target=? AND status=? "
                  "ORDER BY created_at DESC, rowid DESC LIMIT 1", (app, target, LIVE))
    return rows[0] if rows else None


def previous_deployment(app: str, target: str) -> dict | None:
    """현재 LIVE 이전에 성공했던 배포 중 이미지가 다른 가장 최근 것 (롤백 대상)."""
    live = live_deployment(app, target)
    rows = _query("SELECT * FROM deployments WHERE app=? AND target=? AND status=? AND image<>? "
                  "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                  (app, target, SUPERSEDED, live["image"] if live else ""))
    return rows[0] if rows else None


def supersede(app: str, target: str, keep_id: str) -> None:
    _exec("UPDATE deployments SET status=? WHERE app=? AND target=? AND status=? AND id<>?",
          (SUPERSEDED, app, target, LIVE, keep_id))


def list_releases(limit: int = 30) -> list[dict]:
    rels = _query("SELECT * FROM releases ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,))
    for r in rels:
        r["deployments"] = deployments_of(r["id"])
    return rels


def release_done(rid: str) -> bool:
    deps = deployments_of(rid)
    return bool(deps) and all(d["status"] in TERMINAL for d in deps)


# ---- 로그 ----

def add_log(rid: str, scope: str, line: str) -> None:
    _exec("INSERT INTO logs (release_id, scope, ts, line) VALUES (?,?,?,?)",
          (rid, scope, time.time(), line))


def logs_since(rid: str, after_id: int = 0) -> list[dict]:
    return _query("SELECT id, scope, ts, line FROM logs WHERE release_id=? AND id>? ORDER BY id",
                  (rid, after_id))


# ---- 로컬 포트 ----

def local_port(app: str, base: int = 18000) -> int:
    with _lock:
        row = db().execute("SELECT port FROM local_ports WHERE app=?", (app,)).fetchone()
        if row:
            return row["port"]
        used = {r["port"] for r in db().execute("SELECT port FROM local_ports")}
        port = next(p for p in range(base, base + 1000) if p not in used)
        db().execute("INSERT INTO local_ports VALUES (?,?)", (app, port))
        db().commit()
        return port
