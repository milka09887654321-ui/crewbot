from __future__ import annotations
from datetime import datetime, timezone
from db import get_conn

FIELDS = [
    "full_name", "nationality", "dob", "rank", "phone", "whatsapp", "email",
    "english", "experience", "vessel_exp", "certificates", "available_from"
]

def upsert_profile(user_id: int, data: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()

    cols = ",".join(FIELDS)
    placeholders = ",".join(["?"] * (len(FIELDS) + 2))  # user_id + fields + updated_at
    updates = ",".join([f"{f}=excluded.{f}" for f in FIELDS])

    values = [data.get(f) for f in FIELDS]

    sql = f"""
    INSERT INTO profile (user_id,{cols},updated_at)
    VALUES ({placeholders})
    ON CONFLICT(user_id) DO UPDATE SET
        {updates},
        updated_at=excluded.updated_at
    """

    with get_conn() as conn:
        conn.execute(sql, [user_id, *values, now])
        conn.commit()

def get_profile(user_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM profile WHERE user_id=?",
            (user_id,)
        ).fetchone()
        return dict(row) if row else None
