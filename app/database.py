"""Database module for media metadata storage using SQLite."""

import sqlite3
import os
from datetime import datetime
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "/data/media.db")


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the database schema."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS callsigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                callsign_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                media_type TEXT NOT NULL CHECK(media_type IN ('image', 'video', 'audio', 'document')),
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_size INTEGER,
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (callsign_id) REFERENCES callsigns(id) ON DELETE CASCADE
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_media_callsign ON media(callsign_id)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_media_type ON media(media_type)
        """)


# --- Callsign operations ---

def create_callsign(name: str, description: str = "") -> int:
    """Create a new callsign entry. Returns the ID."""
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO callsigns (name, description) VALUES (?, ?)",
            (name.upper().strip(), description.strip()),
        )
        return cursor.lastrowid


def get_all_callsigns() -> list[dict]:
    """Get all callsigns ordered by name."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM callsigns ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]


def get_callsign(callsign_id: int) -> dict | None:
    """Get a single callsign by ID."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM callsigns WHERE id = ?", (callsign_id,)
        ).fetchone()
        return dict(row) if row else None


def update_callsign(callsign_id: int, name: str, description: str):
    """Update callsign details."""
    with get_db() as conn:
        conn.execute(
            "UPDATE callsigns SET name = ?, description = ? WHERE id = ?",
            (name.upper().strip(), description.strip(), callsign_id),
        )


def delete_callsign(callsign_id: int):
    """Delete a callsign and all associated media records."""
    with get_db() as conn:
        conn.execute("DELETE FROM callsigns WHERE id = ?", (callsign_id,))


# --- Media operations ---

def create_media(
    callsign_id: int,
    title: str,
    description: str,
    media_type: str,
    filename: str,
    original_filename: str,
    file_size: int,
) -> int:
    """Create a new media entry. Returns the ID."""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO media
               (callsign_id, title, description, media_type, filename, original_filename, file_size)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (callsign_id, title.strip(), description.strip(), media_type, filename, original_filename, file_size),
        )
        return cursor.lastrowid


def get_media_by_callsign(callsign_id: int, media_type: str | None = None) -> list[dict]:
    """Get all media for a callsign, optionally filtered by type."""
    with get_db() as conn:
        if media_type:
            rows = conn.execute(
                "SELECT * FROM media WHERE callsign_id = ? AND media_type = ? ORDER BY uploaded_at DESC",
                (callsign_id, media_type),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM media WHERE callsign_id = ? ORDER BY uploaded_at DESC",
                (callsign_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_all_media(media_type: str | None = None) -> list[dict]:
    """Get all media, optionally filtered by type."""
    with get_db() as conn:
        if media_type:
            rows = conn.execute(
                """SELECT m.*, c.name as callsign_name
                   FROM media m JOIN callsigns c ON m.callsign_id = c.id
                   WHERE m.media_type = ?
                   ORDER BY m.uploaded_at DESC""",
                (media_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT m.*, c.name as callsign_name
                   FROM media m JOIN callsigns c ON m.callsign_id = c.id
                   ORDER BY m.uploaded_at DESC"""
            ).fetchall()
        return [dict(r) for r in rows]


def get_media(media_id: int) -> dict | None:
    """Get a single media entry by ID."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT m.*, c.name as callsign_name
               FROM media m JOIN callsigns c ON m.callsign_id = c.id
               WHERE m.id = ?""",
            (media_id,),
        ).fetchone()
        return dict(row) if row else None


def update_media(media_id: int, title: str, description: str):
    """Update media metadata."""
    with get_db() as conn:
        conn.execute(
            "UPDATE media SET title = ?, description = ? WHERE id = ?",
            (title.strip(), description.strip(), media_id),
        )


def delete_media(media_id: int) -> str | None:
    """Delete a media entry. Returns the filename for cleanup."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT filename FROM media WHERE id = ?", (media_id,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
            return row["filename"]
    return None


def get_media_count_by_callsign(callsign_id: int) -> int:
    """Get the count of media items for a callsign."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM media WHERE callsign_id = ?",
            (callsign_id,),
        ).fetchone()
        return row["cnt"]
