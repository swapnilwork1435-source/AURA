"""Create or restore a consistent SQLite backup of AURA's local database.

Create:  python backup_database.py
Restore: python backup_database.py --restore path/to/backup.db

Restore first creates a timestamped pre-restore backup. Stop the API and worker
before restoring. This utility deliberately supports SQLite only.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("AURA_DATA_DIR", BACKEND_DIR / "data"))
DATABASE_URL = os.getenv("AURA_DATABASE_URL", f"sqlite:///{DATA_DIR / 'aura.db'}")


def db_path_from_url(url: str) -> Path:
    if not url.startswith("sqlite:///"):
        raise SystemExit("Backup utility currently supports SQLite URLs only.")
    path = Path(url.removeprefix("sqlite:///"))
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def integrity_check(path: Path) -> None:
    with sqlite3.connect(str(path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise SystemExit(f"SQLite integrity check failed: {result}")


def backup(source: Path, destination: Path) -> None:
    if not source.exists():
        raise SystemExit(f"Database does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(destination)) as dst:
        src.backup(dst)
    integrity_check(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", type=Path, help="Backup file to restore")
    parser.add_argument("--output", type=Path, help="Destination for a new backup")
    args = parser.parse_args()
    source = db_path_from_url(DATABASE_URL)
    backup_dir = DATA_DIR / "backups"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if args.restore:
        restore_source = args.restore.resolve()
        if not restore_source.is_file():
            raise SystemExit(f"Backup file not found: {restore_source}")
        integrity_check(restore_source)
        if source.exists():
            safety_copy = backup_dir / f"aura-pre-restore-{stamp}.db"
            backup(source, safety_copy)
            print(f"Pre-restore safety backup: {safety_copy}")
        source.parent.mkdir(parents=True, exist_ok=True)
        temporary = source.with_suffix(source.suffix + ".restore-tmp")
        backup(restore_source, temporary)
        os.replace(temporary, source)
        integrity_check(source)
        print(f"Restored database from: {restore_source}")
        return
    destination = (args.output or (backup_dir / f"aura-{stamp}.db")).resolve()
    backup(source, destination)
    print(f"Backup created and integrity-checked: {destination}")


if __name__ == "__main__":
    main()
