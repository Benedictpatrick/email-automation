import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime
from backend.config import DB_PATH, DEFAULT_SETTINGS

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Leads table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER DEFAULT 1,
            email TEXT UNIQUE NOT NULL,
            first_name TEXT,
            company TEXT,
            job_title TEXT,
            website TEXT,
            notes TEXT,
            custom_hook TEXT,
            email_subject TEXT,
            email_body TEXT,
            status TEXT DEFAULT 'pending',
            sent_at TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    # Activity logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            lead_email TEXT,
            level TEXT DEFAULT 'INFO',
            message TEXT
        )
    """)

    # Populate default settings if missing
    for key, val in DEFAULT_SETTINGS.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, str(val)))

    conn.commit()
    conn.close()

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row["value"]
    return default if default is not None else DEFAULT_SETTINGS.get(key, "")

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (key, str(value)))
    conn.commit()
    conn.close()

def get_all_settings() -> Dict[str, str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    res = {k: v for k, v in DEFAULT_SETTINGS.items()}
    for r in rows:
        res[r["key"]] = r["value"]
    return res

def bulk_insert_leads(lead_list: List[Dict[str, Any]]) -> Dict[str, int]:
    conn = get_connection()
    cursor = conn.cursor()
    inserted = 0
    duplicates = 0

    for item in lead_list:
        email = (item.get("email") or "").strip().lower()
        if not email or "@" not in email:
            continue
        try:
            cursor.execute("""
                INSERT INTO leads (email, first_name, company, job_title, website, notes, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending')
            """, (
                email,
                item.get("first_name", "").strip(),
                item.get("company", "").strip(),
                item.get("job_title", "").strip(),
                item.get("website", "").strip(),
                item.get("notes", "").strip(),
            ))
            inserted += 1
        except sqlite3.IntegrityError:
            duplicates += 1

    conn.commit()
    conn.close()
    return {"inserted": inserted, "duplicates": duplicates}

def get_leads(status: Optional[str] = None, search: Optional[str] = None, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM leads WHERE 1=1"
    params = []

    if status and status != "all":
        query += " AND status = ?"
        params.append(status)

    if search:
        query += " AND (email LIKE ? OR company LIKE ? OR first_name LIKE ? OR job_title LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s, s])

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_lead_by_id(lead_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_lead(lead_id: int, **kwargs):
    if not kwargs:
        return
    conn = get_connection()
    cursor = conn.cursor()
    fields = []
    params = []
    for k, v in kwargs.items():
        fields.append(f"{k} = ?")
        params.append(v)
    params.append(lead_id)

    query = f"UPDATE leads SET {', '.join(fields)} WHERE id = ?"
    cursor.execute(query, params)
    conn.commit()
    conn.close()

def delete_lead(lead_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()

def clear_all_leads():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leads")
    cursor.execute("DELETE FROM activity_logs")
    conn.commit()
    conn.close()

def reset_lead_statuses(target_status: str = "pending"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE leads SET status = ?, sent_at = NULL, error_message = NULL", (target_status,))
    conn.commit()
    conn.close()

def approve_lead(lead_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE leads SET status = 'approved' WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()

def approve_all_generated():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE leads SET status = 'approved' WHERE status = 'generated'")
    conn.commit()
    conn.close()

def get_campaign_stats() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'generated' THEN 1 ELSE 0 END) as generated,
            SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
        FROM leads
    """)
    row = cursor.fetchone()
    conn.close()
    return {
        "total": row["total"] or 0,
        "sent": row["sent"] or 0,
        "pending": row["pending"] or 0,
        "generated": row["generated"] or 0,
        "approved": row["approved"] or 0,
        "failed": row["failed"] or 0
    }

def log_activity(message: str, level: str = "INFO", lead_email: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO activity_logs (lead_email, level, message)
        VALUES (?, ?, ?)
    """, (lead_email, level, message))
    conn.commit()
    conn.close()

def get_recent_logs(limit: int = 100) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

