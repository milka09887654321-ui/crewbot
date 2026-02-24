import sqlite3
from pathlib import Path

DB_PATH = Path("bot.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            nationality TEXT,
            dob TEXT,
            rank TEXT,
            phone TEXT,
            whatsapp TEXT,
            email TEXT,
            english TEXT,
            experience TEXT,
            vessel_exp TEXT,
            certificates TEXT,
            available_from TEXT,
            updated_at TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            user_id INTEGER NOT NULL,
            vacancy_id INTEGER NOT NULL,
            applied_at TEXT NOT NULL,
            PRIMARY KEY (user_id, vacancy_id)
        )
        """)

        conn.commit()
