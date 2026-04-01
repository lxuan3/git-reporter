import json
import os
import sqlite3
from datetime import date
from pathlib import Path

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS daily_snapshots (
    date          TEXT NOT NULL,
    person        TEXT NOT NULL,
    repo          TEXT NOT NULL,
    commits       INTEGER NOT NULL,
    lines_added   INTEGER NOT NULL,
    lines_deleted INTEGER NOT NULL,
    files_changed INTEGER NOT NULL,
    messages      TEXT NOT NULL,
    UNIQUE(date, person, repo)
)
"""

_DEFAULT_DB_PATH = str(Path(__file__).resolve().parent / "git_reporter.db")


def _resolve_db_path(db_path: str) -> str:
    if os.path.isabs(db_path):
        return db_path
    return str(Path(__file__).resolve().parent / db_path)

def _connect(db_path: str) -> sqlite3.Connection:
    db_path = _resolve_db_path(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn

def save_snapshot(report: dict, target_date: date, db_path: str = _DEFAULT_DB_PATH) -> None:
    """将 build_report() 返回的 report 写入 SQLite。同一 (date, person, repo) 幂等。"""
    date_str = target_date.isoformat()
    conn = _connect(db_path)
    try:
        for person in report["persons"]:
            for repo_name, stats in person.repos.items():
                conn.execute(
                    "INSERT OR REPLACE INTO daily_snapshots VALUES (?,?,?,?,?,?,?,?)",
                    (
                        date_str,
                        person.display_name,
                        repo_name,
                        stats.commits,
                        stats.lines_added,
                        stats.lines_deleted,
                        stats.files_changed,
                        json.dumps(stats.messages, ensure_ascii=False),
                    ),
                )
        conn.commit()
    finally:
        conn.close()

def query_range(start: date, end: date, db_path: str = _DEFAULT_DB_PATH) -> list[dict]:
    """返回 [start, end] 日期范围内的所有快照行，按 date ASC 排序。DB 不存在时返回 []。"""
    db_path = _resolve_db_path(db_path)
    if not os.path.exists(db_path):
        return []
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM daily_snapshots WHERE date >= ? AND date <= ? ORDER BY date ASC",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [
            {
                "date": row["date"],
                "person": row["person"],
                "repo": row["repo"],
                "commits": row["commits"],
                "lines_added": row["lines_added"],
                "lines_deleted": row["lines_deleted"],
                "files_changed": row["files_changed"],
                "messages": json.loads(row["messages"]),
            }
            for row in rows
        ]
    finally:
        conn.close()
