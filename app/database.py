"""Database module for media metadata storage.

Reads special callsign (award) data from Quendaward's SQLite database
and stores media metadata in its own separate SQLite database.
"""

import sqlite3
import os
from contextlib import contextmanager

# Quendaward's database (read-only for award/callsign info)
QUENDAWARD_DB_PATH = os.environ.get(
    "QUENDAWARD_DB_PATH", "/quendaward_data/ham_coordinator.db"
)

# Media app's own database
MEDIA_DB_PATH = os.environ.get("MEDIA_DB_PATH", "/data/media.db")


@contextmanager
def get_quendaward_db():
    """Read-only connection to Quendaward's database."""
    conn = sqlite3.connect(
        f"file:{QUENDAWARD_DB_PATH}?mode=ro", uri=True,
        check_same_thread=False, timeout=30.0,
    )
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_media_db():
    """Connection to the media app's own database."""
    conn = sqlite3.connect(MEDIA_DB_PATH, check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize the media database schema."""
    os.makedirs(os.path.dirname(MEDIA_DB_PATH), exist_ok=True)
    with get_media_db() as conn:
        # Groups table must exist before media (media references it)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS media_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                award_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                sort_order INTEGER
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_groups_award ON media_groups(award_id)
        """)
        # Migration: add allowed_types column to media_groups
        try:
            conn.execute("ALTER TABLE media_groups ADD COLUMN allowed_types TEXT")
        except Exception:
            pass  # Column already exists

        # Check current state of media table
        table_info = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='media'"
        ).fetchone()

        if table_info is None:
            # Fresh install – create with full schema including youtube
            conn.execute("""
                CREATE TABLE media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    award_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    media_type TEXT NOT NULL CHECK(media_type IN ('image', 'video', 'audio', 'document', 'youtube')),
                    filename TEXT NOT NULL DEFAULT '',
                    original_filename TEXT NOT NULL DEFAULT '',
                    file_size INTEGER,
                    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                    sort_order INTEGER,
                    group_id INTEGER REFERENCES media_groups(id) ON DELETE SET NULL,
                    youtube_url TEXT
                )
            """)
        else:
            # Existing table – run column migrations
            for migration in [
                "ALTER TABLE media ADD COLUMN sort_order INTEGER",
                "ALTER TABLE media ADD COLUMN group_id INTEGER REFERENCES media_groups(id) ON DELETE SET NULL",
                "ALTER TABLE media ADD COLUMN youtube_url TEXT",
            ]:
                try:
                    conn.execute(migration)
                except Exception:
                    pass  # Column already exists

            # Migration: update CHECK constraint to include 'youtube' via table recreation
            current_sql = table_info["sql"] or ""
            if "'youtube'" not in current_sql:
                conn.execute("""
                    CREATE TABLE media_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        award_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        description TEXT,
                        media_type TEXT NOT NULL CHECK(media_type IN ('image', 'video', 'audio', 'document', 'youtube')),
                        filename TEXT NOT NULL DEFAULT '',
                        original_filename TEXT NOT NULL DEFAULT '',
                        file_size INTEGER,
                        uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                        sort_order INTEGER,
                        group_id INTEGER REFERENCES media_groups(id) ON DELETE SET NULL,
                        youtube_url TEXT
                    )
                """)
                conn.execute("""
                    INSERT INTO media_new
                    SELECT id, award_id, title, description, media_type,
                           COALESCE(filename, ''), COALESCE(original_filename, ''),
                           file_size, uploaded_at, sort_order, group_id, youtube_url
                    FROM media
                """)
                conn.execute("DROP TABLE media")
                conn.execute("ALTER TABLE media_new RENAME TO media")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_media_award ON media(award_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_media_type ON media(media_type)")


# --- Authentication (standalone, env-var based) ---

_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
_ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def authenticate_admin(username: str, password: str) -> bool:
    """Authenticate against the ADMIN_USERNAME / ADMIN_PASSWORD env vars.

    Returns True on success, False on failure.
    """
    if not _ADMIN_PASSWORD:
        # No password configured – deny all access to prevent open installs
        return False
    return username.strip() == _ADMIN_USERNAME and password == _ADMIN_PASSWORD


# --- Award/Callsign operations (read from Quendaward) ---

def get_all_callsigns() -> list[dict]:
    """Get all active awards (special callsigns) from Quendaward's database."""
    with get_quendaward_db() as conn:
        rows = conn.execute(
            """SELECT id, name, description, start_date, end_date,
                      image_data, image_type, qrz_link
               FROM awards
               WHERE is_active = 1
               ORDER BY name"""
        ).fetchall()
        return [dict(r) for r in rows]


def get_callsign(award_id: int) -> dict | None:
    """Get a single award/callsign by ID from Quendaward's database."""
    with get_quendaward_db() as conn:
        row = conn.execute(
            """SELECT id, name, description, start_date, end_date,
                      image_data, image_type, qrz_link
               FROM awards WHERE id = ?""",
            (award_id,),
        ).fetchone()
        return dict(row) if row else None


# --- Group operations (own database) ---

def create_group(award_id: int, name: str, allowed_types: list[str] | None = None) -> int:
    """Create a new media group for an award. Returns the group ID.

    ``allowed_types`` is an optional list like ``["image", "video"]``.
    ``None`` means all types are allowed.
    """
    types_csv = ",".join(allowed_types) if allowed_types else None
    with get_media_db() as conn:
        # Place new group at the end
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_pos FROM media_groups WHERE award_id = ?",
            (award_id,),
        ).fetchone()
        cursor = conn.execute(
            "INSERT INTO media_groups (award_id, name, sort_order, allowed_types) VALUES (?, ?, ?, ?)",
            (award_id, name.strip(), row["next_pos"], types_csv),
        )
        return cursor.lastrowid


def get_groups_by_callsign(award_id: int) -> list[dict]:
    """Get all groups for a callsign, ordered by sort_order."""
    with get_media_db() as conn:
        rows = conn.execute(
            "SELECT * FROM media_groups WHERE award_id = ? ORDER BY COALESCE(sort_order, 999999) ASC, id ASC",
            (award_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_group(group_id: int, name: str, allowed_types: list[str] | None = None):
    """Update a media group's name and allowed types."""
    types_csv = ",".join(allowed_types) if allowed_types else None
    with get_media_db() as conn:
        conn.execute(
            "UPDATE media_groups SET name = ?, allowed_types = ? WHERE id = ?",
            (name.strip(), types_csv, group_id),
        )


def delete_group(group_id: int):
    """Delete a group. Media in this group become ungrouped (group_id → NULL)."""
    with get_media_db() as conn:
        conn.execute("UPDATE media SET group_id = NULL WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM media_groups WHERE id = ?", (group_id,))


def assign_media_to_group(group_id: int | None, media_ids: list[int]):
    """Batch-assign media items to a group (or ungroup them when group_id is None)."""
    with get_media_db() as conn:
        for mid in media_ids:
            conn.execute(
                "UPDATE media SET group_id = ? WHERE id = ?",
                (group_id, mid),
            )


def update_group_order(group_ids: list[int]):
    """Persist a new sort order for groups."""
    with get_media_db() as conn:
        for position, gid in enumerate(group_ids, start=1):
            conn.execute(
                "UPDATE media_groups SET sort_order = ? WHERE id = ?",
                (position, gid),
            )


# --- Media operations (own database) ---

def create_media(
    award_id: int,
    title: str,
    description: str,
    media_type: str,
    filename: str,
    original_filename: str,
    file_size: int,
    group_id: int | None = None,
    youtube_url: str | None = None,
) -> int:
    """Create a new media entry. Returns the ID."""
    with get_media_db() as conn:
        cursor = conn.execute(
            """INSERT INTO media
               (award_id, title, description, media_type, filename, original_filename, file_size, group_id, youtube_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (award_id, title.strip(), description.strip(), media_type,
             filename, original_filename, file_size, group_id, youtube_url),
        )
        return cursor.lastrowid


def get_media_by_callsign(award_id: int, media_type: str | None = None) -> list[dict]:
    """Get all media for an award/callsign, optionally filtered by type."""
    with get_media_db() as conn:
        if media_type:
            rows = conn.execute(
                """SELECT * FROM media WHERE award_id = ? AND media_type = ?
                   ORDER BY COALESCE(sort_order, 999999) ASC, uploaded_at DESC""",
                (award_id, media_type),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM media WHERE award_id = ?
                   ORDER BY COALESCE(sort_order, 999999) ASC, uploaded_at DESC""",
                (award_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_all_media(media_type: str | None = None) -> list[dict]:
    """Get all media, optionally filtered by type, with callsign names resolved."""
    # First get all media from our database
    with get_media_db() as conn:
        if media_type:
            rows = conn.execute(
                "SELECT * FROM media WHERE media_type = ? ORDER BY uploaded_at DESC",
                (media_type,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM media ORDER BY uploaded_at DESC"
            ).fetchall()
        media_items = [dict(r) for r in rows]

    if not media_items:
        return []

    # Resolve callsign names from Quendaward's database
    callsign_map = {c["id"]: c["name"] for c in get_all_callsigns()}
    # Also try to resolve inactive awards for orphaned media
    for item in media_items:
        cs = callsign_map.get(item["award_id"])
        if not cs:
            info = get_callsign(item["award_id"])
            cs = info["name"] if info else f"Unknown (ID {item['award_id']})"
        item["callsign_name"] = cs

    return media_items


def get_media(media_id: int) -> dict | None:
    """Get a single media entry by ID with callsign name resolved."""
    with get_media_db() as conn:
        row = conn.execute(
            "SELECT * FROM media WHERE id = ?", (media_id,)
        ).fetchone()
        if not row:
            return None
        item = dict(row)

    info = get_callsign(item["award_id"])
    item["callsign_name"] = info["name"] if info else f"Unknown (ID {item['award_id']})"
    return item


def update_media_order(media_ids: list[int]):
    """Persist a new sort order for a list of media items.

    ``media_ids`` is the ordered list of IDs as the admin arranged them.
    Items are assigned sort_order 1, 2, 3, … in that sequence.
    """
    with get_media_db() as conn:
        for position, media_id in enumerate(media_ids, start=1):
            conn.execute(
                "UPDATE media SET sort_order = ? WHERE id = ?",
                (position, media_id),
            )


def update_media(media_id: int, title: str, description: str, group_id: int | None = None):
    """Update media metadata."""
    with get_media_db() as conn:
        conn.execute(
            "UPDATE media SET title = ?, description = ?, group_id = ? WHERE id = ?",
            (title.strip(), description.strip(), group_id, media_id),
        )


def delete_media(media_id: int) -> str | None:
    """Delete a media entry. Returns the filename for cleanup."""
    with get_media_db() as conn:
        row = conn.execute(
            "SELECT filename FROM media WHERE id = ?", (media_id,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM media WHERE id = ?", (media_id,))
            return row["filename"]
    return None


def get_media_count_by_callsign(award_id: int) -> int:
    """Get the count of media items for an award/callsign."""
    with get_media_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM media WHERE award_id = ?",
            (award_id,),
        ).fetchone()
        return row["cnt"]
