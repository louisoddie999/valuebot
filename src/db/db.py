"""SQLite helper: connection, schema init, config loader."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_config() -> dict:
    with open(PROJECT_ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_db_path() -> Path:
    env = os.getenv("DB_PATH")          # Render points at the slim serve DB
    if env:
        p = Path(env)
        return p if p.is_absolute() else PROJECT_ROOT / p
    cfg = load_config()
    db_path = PROJECT_ROOT / cfg["paths"]["db"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema() -> None:
    schema_sql = (PROJECT_ROOT / "src" / "db" / "schema.sql").read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(schema_sql)
    print(f"Schema initialised at {get_db_path()}")


if __name__ == "__main__":
    init_schema()
