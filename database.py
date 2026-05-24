"""
database.py — SQLite хранилище для всех конкурсов и действий
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "contests.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS contests (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            vk_post_id      TEXT UNIQUE,          -- owner_id_post_id
            owner_id        INTEGER,              -- id группы (отрицательный)
            post_id         INTEGER,
            title           TEXT,
            text            TEXT,
            found_at        TEXT,
            end_date        TEXT,                 -- предполагаемая дата окончания
            status          TEXT DEFAULT 'active',-- active | winner | loser | cleaned
            repost_id       INTEGER,              -- id нашего репоста на стене
            joined_groups   TEXT DEFAULT '[]',    -- json-список групп, в которые вступили
            liked            INTEGER DEFAULT 0,
            commented        INTEGER DEFAULT 0,
            conditions_raw  TEXT,                 -- сырой текст условий
            notes           TEXT
        );

        CREATE TABLE IF NOT EXISTS actions_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            contest_id  INTEGER,
            action      TEXT,
            detail      TEXT,
            ts          TEXT DEFAULT (datetime('now','localtime'))
        );
        """)
    print("[DB] База данных инициализирована")


def add_contest(owner_id: int, post_id: int, text: str, end_date: str,
                conditions_raw: str) -> int | None:
    """Добавляет конкурс. Возвращает id или None если уже есть."""
    vk_post_id = f"{owner_id}_{post_id}"
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM contests WHERE vk_post_id=?", (vk_post_id,)
        ).fetchone()
        if existing:
            return None
        cur = conn.execute("""
            INSERT INTO contests (vk_post_id, owner_id, post_id, text,
                                  found_at, end_date, conditions_raw)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (vk_post_id, owner_id, post_id, text[:2000],
              datetime.now().isoformat(), end_date, conditions_raw))
        return cur.lastrowid


def get_active_contests():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM contests WHERE status='active'"
        ).fetchall()


def update_contest(contest_id: int, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [contest_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE contests SET {sets} WHERE id=?", vals)


def log_action(contest_id: int, action: str, detail: str = ""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO actions_log (contest_id, action, detail) VALUES (?,?,?)",
            (contest_id, action, detail)
        )


def get_contests_to_check():
    """Конкурсы у которых end_date прошёл и статус ещё active."""
    now = datetime.now().isoformat()
    with get_conn() as conn:
        return conn.execute("""
            SELECT * FROM contests
            WHERE status='active' AND end_date IS NOT NULL AND end_date < ?
        """, (now,)).fetchall()
