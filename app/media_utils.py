"""Utilities for media file handling."""

import os
import uuid
from pathlib import Path

MEDIA_DIR = os.environ.get("MEDIA_DIR", "/data/media")

ALLOWED_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"},
    "video": {".mp4", ".webm", ".avi", ".mov", ".mkv"},
    "audio": {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"},
    "document": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx"},
}

MEDIA_TYPE_ICONS = {
    "image": "\U0001f5bc\ufe0f",
    "video": "\U0001f3ac",
    "audio": "\U0001f3b5",
    "document": "\U0001f4c4",
}

ALL_ALLOWED = set()
for exts in ALLOWED_EXTENSIONS.values():
    ALL_ALLOWED.update(exts)


def detect_media_type(filename: str) -> str | None:
    """Detect the media type from a filename extension."""
    ext = Path(filename).suffix.lower()
    for media_type, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return media_type
    return None


def save_uploaded_file(uploaded_file) -> tuple[str, int]:
    """Save an uploaded file to disk. Returns (stored_filename, file_size)."""
    os.makedirs(MEDIA_DIR, exist_ok=True)
    ext = Path(uploaded_file.name).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(MEDIA_DIR, stored_name)
    data = uploaded_file.getbuffer()
    with open(file_path, "wb") as f:
        f.write(data)
    return stored_name, len(data)


def delete_media_file(filename: str):
    """Remove a media file from disk."""
    file_path = os.path.join(MEDIA_DIR, filename)
    if os.path.exists(file_path):
        os.remove(file_path)


def get_media_path(filename: str) -> str:
    """Get the full path for a media file."""
    return os.path.join(MEDIA_DIR, filename)


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
