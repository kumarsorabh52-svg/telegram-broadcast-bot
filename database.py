#!/usr/bin/env python3
# ============================================================
#   DATABASE - Har admin ke groups alag stored hain
# ============================================================

import sqlite3
import logging

logger = logging.getLogger(__name__)
DB_PATH = "bot_data.db"


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS groups (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                group_id   INTEGER NOT NULL,
                group_name TEXT NOT NULL,
                added_at   TEXT DEFAULT (datetime('now')),
                is_active  INTEGER DEFAULT 1,
                UNIQUE(user_id, group_id)
            );
            CREATE TABLE IF NOT EXISTS stats (
                user_id       INTEGER PRIMARY KEY,
                announcements INTEGER DEFAULT 0,
                polls         INTEGER DEFAULT 0,
                delivered     INTEGER DEFAULT 0,
                failed        INTEGER DEFAULT 0
            );
        """)
        self.conn.commit()

    def register_user(self, user_id: int, username: str):
        c = self.conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
                  (user_id, username))
        c.execute("INSERT OR IGNORE INTO stats (user_id) VALUES (?)", (user_id,))
        self.conn.commit()

    def register_group(self, user_id: int, group_id: int, group_name: str):
        c = self.conn.cursor()
        c.execute("""
            INSERT INTO groups (user_id, group_id, group_name)
            VALUES (?,?,?)
            ON CONFLICT(user_id, group_id) DO UPDATE SET
                group_name = excluded.group_name,
                is_active = 1
        """, (user_id, group_id, group_name))
        self.conn.commit()
        logger.info(f"Group registered: {group_name} for user {user_id}")

    def get_user_groups(self, user_id: int) -> list:
        c = self.conn.cursor()
        c.execute("""
            SELECT group_id, group_name FROM groups
            WHERE user_id=? AND is_active=1
            ORDER BY group_name ASC
        """, (user_id,))
        return [dict(r) for r in c.fetchall()]

    def get_stats(self, user_id: int) -> dict:
        c = self.conn.cursor()
        c.execute("SELECT * FROM stats WHERE user_id=?", (user_id,))
        row = c.fetchone()
        groups = len(self.get_user_groups(user_id))
        if not row:
            return {"groups": groups, "announcements": 0,
                    "polls": 0, "delivered": 0, "failed": 0}
        return {"groups": groups, "announcements": row["announcements"],
                "polls": row["polls"], "delivered": row["delivered"],
                "failed": row["failed"]}

    def update_stats(self, user_id: int, mode: str, success: int, failed: int):
        c = self.conn.cursor()
        if mode == "announce":
            c.execute("""
                UPDATE stats SET
                    announcements = announcements+1,
                    delivered = delivered+?,
                    failed = failed+?
                WHERE user_id=?
            """, (success, failed, user_id))
        else:
            c.execute("""
                UPDATE stats SET
                    polls = polls+1,
                    delivered = delivered+?,
                    failed = failed+?
                WHERE user_id=?
            """, (success, failed, user_id))
        self.conn.commit()
