"""GN-092: validated, atomic SQLite backup/restore with optional diagnostic logs.

No audio is archived. Stop the server before restoration. The SQLite backup
API provides a consistent snapshot even with transactions in progress.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile

from app.contracts import ContractBundle, Match
from app.logging_setup import DEFAULT_LOG
from app.storage import DEFAULT_DB

FORMAT = "game-now-backup-v1"
DB_ENTRY = "game_now.sqlite3"
MANIFEST = "manifest.json"
MAX_DB = 256 * 1024 * 1024
MAX_LOG = 12 * 1024 * 1024
LOG_NAMES = frozenset(["game_now.log", "game_now.log.1", "game_now.log.2", "game_now.log.3"])


class BackupError(ValueError):
    """The local archive or database cannot safely be backed up/restored."""


def _digest(path: Path) -> str:
    result = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def _verify_sqlite(path: Path) -> list[str]:
    """Validate SQLite integrity, expected tables and model references before use."""
    try:
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_DB:
            raise BackupError("SQLite file missing, empty or too large")
        with sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise BackupError("SQLite integrity check failed")
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise BackupError("Broken SQLite foreign-key references")
            names = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            required = {"matches", "snapshots", "roster_positions",
                        "match_flow", "match_corrections"}
            if not required <= names:
                raise BackupError("Not a compatible Game Now SQLite database")
            matches = {
                ident: Match.model_validate_json(payload)
                for ident, payload in conn.execute("SELECT id,payload FROM matches")
            }
            if any(ident != match.id for ident, match in matches.items()):
                raise BackupError("Mismatch between match row ID and payload")
            snapshots = {
                ident: ContractBundle.model_validate_json(payload)
                for ident, payload in conn.execute("SELECT match_id,payload FROM snapshots")
            }
            if set(matches) != set(snapshots):
                raise BackupError("A match is missing its saved state")
            for ident, bundle in snapshots.items():
                if bundle.match != matches[ident]:
                    raise BackupError("Match and snapshot do not agree")
            return sorted(matches)
    except BackupError:
        raise
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise BackupError("Invalid or incompatible SQLite backup") from exc


def _snapshot(source: Path, destination: Path) -> list[str]:
    if not source.is_file():
        raise BackupError("Source SQLite file not found")
    try:
        with sqlite3.connect(
            f"file:{source.resolve().as_posix()}?mode=ro", uri=True
        ) as origin, sqlite3.connect(destination) as target:
            origin.backup(target)
    except (OSError, sqlite3.Error) as exc:
        raise BackupError("Could not create SQLite snapshot") from exc
    return _verify_sqlite(destination)


def create_backup(
    database: Path, archive: Path, *, include_logs: bool = False,
    log_file: Path = DEFAULT_LOG,
) -> dict:
    """Export a consistent database copy plus optional bounded diagnostic logs."""
    database, archive, log_file = Path(database), Path(archive), Path(log_file)
    if archive.exists():
        raise BackupError("Backup output already exists; choose a new filename")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="game-now-backup-") as working:
        tempdb = Path(working) / DB_ENTRY
        match_ids = _snapshot(database, tempdb)
        db_metadata = {"name": DB_ENTRY, "bytes": tempdb.stat().st_size,
                       "sha256": _digest(tempdb)}
        log_paths: list[tuple[str, Path]] = []
        if include_logs:
            for suffix in ("", ".1", ".2", ".3"):
                current = Path(str(log_file) + suffix)
                if current.is_file():
                    if current.is_symlink() or current.stat().st_size > MAX_LOG:
                        raise BackupError("Invalid diagnostic log file")
                    log_paths.append((current.name, current))
            if len({name for name, _ in log_paths}) != len(log_paths):
                raise BackupError("Duplicate log filenames")
        logs = [
            {"name": name, "bytes": path.stat().st_size, "sha256": _digest(path)}
            for name, path in log_paths
        ]
        if sum(x["bytes"] for x in logs) > MAX_LOG:
            raise BackupError("Diagnostic logs exceed archive budget")
        if any(entry["name"] not in LOG_NAMES for entry in logs):
            raise BackupError("Unsupported log filename")
        manifest = {
            "format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
            "database": db_metadata, "match_ids": match_ids, "logs": logs,
            "audio_included": False,
        }
        fd, temporary = tempfile.mkstemp(
            prefix=".game-now-", suffix=".zip", dir=archive.parent
        )
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as out:
                out.write(tempdb, DB_ENTRY)
                for name, path in log_paths:
                    out.write(path, "logs/" + name)
                out.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False))
            if archive.exists():
                raise BackupError("Backup output already exists")
            os.replace(temporary, archive)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return {"result": "backup_created", "archive": str(archive),
            "match_count": len(match_ids), "diagnostic_logs": len(logs),
            "audio_included": False}


def _validate_manifest(archive: zipfile.ZipFile) -> dict:
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    if len(names) != len(set(names)) or len(names) > 6:
        raise BackupError("Duplicate or excessive ZIP entries")
    if MANIFEST not in names or DB_ENTRY not in names:
        raise BackupError("Backup manifest or SQLite file missing")
    for item in entries:
        mode = (item.external_attr >> 16)
        if (item.is_dir() or stat.S_IFMT(mode) == stat.S_IFLNK
                or item.filename.startswith("/") or "\\" in item.filename
                or ".." in item.filename.split("/")
                or item.file_size > MAX_DB):
            raise BackupError("Unsafe ZIP entry")
    if archive.getinfo(MANIFEST).file_size > 100_000:
        raise BackupError("Backup manifest too large")
    try:
        manifest = json.loads(archive.read(MANIFEST))
        assert isinstance(manifest, dict) and manifest["format"] == FORMAT
        assert manifest["audio_included"] is False
        db = manifest["database"]
        assert db["name"] == DB_ENTRY and 0 < db["bytes"] <= MAX_DB
        assert re.fullmatch("[0-9a-f]{64}", db["sha256"])
        assert archive.getinfo(DB_ENTRY).file_size == db["bytes"]
        assert isinstance(manifest["match_ids"], list)
        assert all(isinstance(x, str) for x in manifest["match_ids"])
        logs = manifest["logs"]
        assert isinstance(logs, list) and len(logs) <= 4
        assert len({x["name"] for x in logs}) == len(logs)
        expected_names = {MANIFEST, DB_ENTRY}
        for log in logs:
            assert log["name"] in LOG_NAMES
            assert 0 <= log["bytes"] <= MAX_LOG
            assert re.fullmatch("[0-9a-f]{64}", log["sha256"])
            entry_name = "logs/" + log["name"]
            assert archive.getinfo(entry_name).file_size == log["bytes"]
            expected_names.add(entry_name)
        assert set(names) == expected_names
        assert sum(log["bytes"] for log in logs) <= MAX_LOG
    except (KeyError, TypeError, ValueError, AssertionError, zipfile.BadZipFile) as exc:
        raise BackupError("Backup manifest is inconsistent or unsupported") from exc
    return manifest


def restore_backup(
    archive: Path, database: Path, *, replace_existing: bool = False,
    logs_directory: Path | None = None,
) -> dict:
    """Validate everything, then atomically install SQLite at a local path."""
    archive, database = Path(archive), Path(database)
    if not archive.is_file():
        raise BackupError("Archive not found")
    if database.exists() and not replace_existing:
        raise BackupError("Destination SQLite exists; refuse destructive restore")
    if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm")):
        raise BackupError("SQLite WAL/SHM files exist; stop the server before restore")
    try:
        with zipfile.ZipFile(archive, "r") as pack:
            manifest = _validate_manifest(pack)
            if logs_directory is not None:
                logs_directory = Path(logs_directory)
                for item in manifest["logs"]:
                    if (logs_directory / item["name"]).exists():
                        raise BackupError("Log destination exists; choose an empty directory")
            database.parent.mkdir(parents=True, exist_ok=True)
            fd, scratch_name = tempfile.mkstemp(
                prefix=".game-now-restore-", suffix=".sqlite3", dir=database.parent
            )
            os.close(fd)
            scratch = Path(scratch_name)
            try:
                with pack.open(DB_ENTRY, "r") as source, scratch.open("wb") as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                    target.flush()
                    os.fsync(target.fileno())
                if _digest(scratch) != manifest["database"]["sha256"]:
                    raise BackupError("SQLite checksum mismatch")
                match_ids = _verify_sqlite(scratch)
                if match_ids != manifest["match_ids"]:
                    raise BackupError("Backup match manifest does not match SQLite")
                for item in manifest["logs"]:
                    if sha256(pack.read("logs/" + item["name"])).hexdigest() != item["sha256"]:
                        raise BackupError("Diagnostic log checksum mismatch")
                if database.exists() and not replace_existing:
                    raise BackupError("Destination SQLite now exists")
                os.replace(scratch, database)
                if logs_directory is not None and manifest["logs"]:
                    logs_directory.mkdir(parents=True, exist_ok=True)
                    for item in manifest["logs"]:
                        # Fixed filenames validated above; extract no archive paths.
                        (logs_directory / item["name"]).write_bytes(
                            pack.read("logs/" + item["name"])
                        )
            finally:
                scratch.unlink(missing_ok=True)
    except BackupError:
        raise
    except (OSError, sqlite3.Error, zipfile.BadZipFile, EOFError) as exc:
        raise BackupError("Could not verify or restore backup") from exc
    return {"result": "backup_restored", "database": str(database),
            "match_count": len(match_ids),
            "logs_restored": len(manifest["logs"]) if logs_directory else 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GN-092: local Game Now SQLite backup")
    cmd = parser.add_subparsers(dest="command", required=True)
    create = cmd.add_parser("backup")
    create.add_argument("--db", type=Path, default=DEFAULT_DB)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--include-logs", action="store_true")
    create.add_argument("--log-file", type=Path, default=DEFAULT_LOG)
    restore = cmd.add_parser("restore")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--db", type=Path, default=DEFAULT_DB)
    restore.add_argument("--replace-existing", action="store_true")
    restore.add_argument("--logs-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            result = create_backup(args.db, args.output, include_logs=args.include_logs,
                                   log_file=args.log_file)
        else:
            result = restore_backup(args.archive, args.db, replace_existing=args.replace_existing,
                                    logs_directory=args.logs_dir)
    except BackupError as exc:
        parser.exit(2, f"GN-092 backup error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
