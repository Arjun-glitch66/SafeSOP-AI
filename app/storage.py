"""Where original PDFs live. The database stores paths relative to DATA_DIR, so the data folder
(or a Docker volume) can move. Absolute paths from older databases still resolve."""
from pathlib import Path

from app import config


def to_stored_path(path):
    """The value to store for a file: relative to DATA_DIR when it is inside it."""
    path = Path(path)
    try:
        return path.resolve().relative_to(Path(config.DATA_DIR).resolve()).as_posix()
    except ValueError:
        return str(path)


def resolve(stored_path):
    path = Path(stored_path)
    return path if path.is_absolute() else Path(config.DATA_DIR) / path
