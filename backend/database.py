"""SQLite 数据库：预测记录与训练单元信息的持久化。

对应课程设计架构要求中的"数据库"层。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "phm.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                unit_id TEXT,
                sensor_count INTEGER,
                cycles_used INTEGER,
                predicted_rul REAL NOT NULL,
                rf_rul REAL,
                health_level TEXT NOT NULL,
                advice TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit INTEGER NOT NULL UNIQUE,
                max_cycle INTEGER NOT NULL,
                mean_rul REAL NOT NULL
            )
            """
        )


def insert_prediction(
    unit_id: str,
    sensor_count: int,
    cycles_used: int,
    predicted_rul: float,
    rf_rul: float | None,
    health_level: str,
    advice: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO predictions (created_at, unit_id, sensor_count, cycles_used,"
            " predicted_rul, rf_rul, health_level, advice) VALUES (?,?,?,?,?,?,?,?)",
            (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                unit_id,
                sensor_count,
                cycles_used,
                predicted_rul,
                rf_rul,
                health_level,
                advice,
            ),
        )
        return cur.lastrowid


def list_predictions(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM predictions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_unit(unit: int, max_cycle: int, mean_rul: float):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO units (unit, max_cycle, mean_rul) VALUES (?,?,?)"
            " ON CONFLICT(unit) DO UPDATE SET max_cycle=excluded.max_cycle,"
            " mean_rul=excluded.mean_rul",
            (unit, max_cycle, mean_rul),
        )


def list_units(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM units ORDER BY unit LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
