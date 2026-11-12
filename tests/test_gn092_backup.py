"""GN-092: real local SQLite roundtrip, safe archive/log handling, CLI."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import stat
import zipfile

import pytest

from app.configuration import MatchConfig, RosterPlayer
from app.contracts import AudioSource
from app.storage import SQLiteStore
from scripts.gn092_backup import BackupError, create_backup, restore_backup, main
import scripts.gn092_backup as backup_module


def config(id_="match-092"):
    return MatchConfig.model_validate({
        "id": id_,
        "home": {"id": "home-092", "name": "Azul", "short_name": "AZU",
                 "color": "#1122FF", "attack_direction": "left_to_right"},
        "away": {"id": "away-092", "name": "Vermelho", "short_name": "VER",
                 "color": "#FF2211", "attack_direction": "right_to_left"},
        "period": "first_half", "match_seconds": 22, "home_score": 1,
    })


def sample_db(path: Path) -> SQLiteStore:
    store = SQLiteStore(path)
    store.create_match(config())
    roster = [
        RosterPlayer(id="player-092", team_id="home-092", name="Caio", number=9,
                     aliases=["Caiozinho"], position="forward"),
        RosterPlayer(id="keeper-092", team_id="away-092", name="Beto", number=1,
                     position="goalkeeper"),
    ]
    assert len(store.replace_roster("match-092", roster)) == 2
    source = AudioSource(id="radio-092", name="Rádio Teste", kind="radio",
                         url="https://example.org/radio.mp3")
    assert len(store.replace_sources("match-092", [source])) == 1
    return store


@pytest.mark.parametrize("compatible", [True, False])
def test_snapshot_closes_every_connection_even_when_validation_fails(tmp_path, monkeypatch, compatible):
    source = tmp_path / "source.sqlite3"
    if compatible:
        sample_db(source)
    else:
        conn = sqlite3.connect(source)
        conn.execute("CREATE TABLE unrelated (value TEXT)")
        conn.close()
    connections = []
    connect = sqlite3.connect

    def tracked_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        connections.append(conn)
        return conn

    monkeypatch.setattr(backup_module.sqlite3, "connect", tracked_connect)
    if compatible:
        backup_module._snapshot(source, tmp_path / "snapshot.sqlite3")
    else:
        with pytest.raises(BackupError, match="compatible"):
            backup_module._snapshot(source, tmp_path / "snapshot.sqlite3")
    assert len(connections) == 3  # origin, destination, verification
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_roundtrip_preserves_match_roster_sources_and_sqlite_state(tmp_path: Path):
    source = tmp_path / "orig" / "game.sqlite3"
    original = sample_db(source)
    before = original.get_state("match-092")
    positions = original.get_roster("match-092")
    backup = tmp_path / "secure" / "game-now.zip"
    result = create_backup(source, backup)
    assert result["result"] == "backup_created"
    assert result["match_count"] == 1 and result["diagnostic_logs"] == 0
    restored_path = tmp_path / "new" / "game.sqlite3"
    response = restore_backup(backup, restored_path)
    assert response["match_count"] == 1
    restored = SQLiteStore(restored_path)
    assert restored.get_match("match-092") == original.get_match("match-092")
    assert restored.get_state("match-092") == before
    assert restored.get_roster("match-092") == positions
    assert restored.get_sources("match-092") == original.get_sources("match-092")
    with sqlite3.connect(restored_path) as conn:
        assert conn.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    with zipfile.ZipFile(backup) as pack:
        manifest = json.loads(pack.read("manifest.json"))
        assert set(pack.namelist()) == {"manifest.json", "game_now.sqlite3"}
        assert manifest["audio_included"] is False
        assert manifest["match_ids"] == ["match-092"]
        assert manifest["database"]["sha256"] == sha256(pack.read("game_now.sqlite3")).hexdigest()


def test_optional_log_export_requires_opt_in_and_restores_only_diagnostics(tmp_path: Path):
    db = tmp_path / "database.sqlite3"
    sample_db(db)
    logfile = tmp_path / "logs" / "game_now.log"
    logfile.parent.mkdir()
    logfile.write_text('{"event":"http_request","status":200}\n', encoding="utf-8")
    (logfile.parent / "game_now.log.1").write_text("rotated\n", encoding="utf-8")
    archive = tmp_path / "archive.zip"
    output = create_backup(db, archive, include_logs=True, log_file=logfile)
    assert output["diagnostic_logs"] == 2
    with zipfile.ZipFile(archive) as pack:
        names = set(pack.namelist())
        assert names == {"manifest.json", "game_now.sqlite3",
                         "logs/game_now.log", "logs/game_now.log.1"}
        assert not any("audio" in name or "mp3" in name or "wav" in name for name in names)
    restored_logs = tmp_path / "restored-logs"
    result = restore_backup(archive, tmp_path / "restored.sqlite3", logs_directory=restored_logs)
    assert result["logs_restored"] == 2
    assert (restored_logs / "game_now.log").read_bytes() == logfile.read_bytes()
    assert (restored_logs / "game_now.log.1").read_text() == "rotated\n"


def test_missing_source_is_not_silently_created(tmp_path: Path):
    with pytest.raises(BackupError, match="not found"):
        create_backup(tmp_path / "notfound.sqlite3", tmp_path / "backup.zip")
    assert not (tmp_path / "notfound.sqlite3").exists()


def test_refuse_to_replace_existing_archive_or_database(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    sample_db(source)
    archive = tmp_path / "backup.zip"
    create_backup(source, archive)
    with pytest.raises(BackupError, match="already exists"):
        create_backup(source, archive)
    dest = tmp_path / "destination.sqlite3"
    sample_db(dest)
    before = dest.read_bytes()
    with pytest.raises(BackupError, match="exists"):
        restore_backup(archive, dest)
    assert dest.read_bytes() == before
    assert restore_backup(archive, dest, replace_existing=True)["result"] == "backup_restored"
    with (tmp_path / "destination.sqlite3-wal").open("wb") as fp:
        fp.write(b"")
    with pytest.raises(BackupError, match="WAL/SHM"):
        restore_backup(archive, dest, replace_existing=True)


def test_modified_database_checksum_aborts_restore(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    sample_db(source)
    archive = tmp_path / "valid.zip"
    create_backup(source, archive)
    altered = tmp_path / "altered.zip"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(altered, "w") as out:
        for name in original.namelist():
            content = original.read(name)
            out.writestr(name, content + b"X" if name == "game_now.sqlite3" else content)
    dest = tmp_path / "restored.sqlite3"
    with pytest.raises(BackupError, match="manifest|checksum"):
        restore_backup(altered, dest)
    assert not dest.exists()


def test_zip_slip_duplicate_unknown_and_symbolic_link_are_blocked(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    sample_db(source)
    archive = tmp_path / "good.zip"
    create_backup(source, archive)
    for suffix, extra in (
        ("traversal", "../escape.txt"),
        ("unknown", "audio.wav"),
    ):
        tampered = tmp_path / f"{suffix}.zip"
        with zipfile.ZipFile(archive) as original, zipfile.ZipFile(tampered, "w") as out:
            for name in original.namelist():
                out.writestr(name, original.read(name))
            out.writestr(extra, b"no")
        with pytest.raises(BackupError):
            restore_backup(tampered, tmp_path / f"{suffix}.sqlite3")
        assert not (tmp_path / "escape.txt").exists()
    symlink_archive = tmp_path / "link.zip"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(symlink_archive, "w") as out:
        for name in original.namelist():
            info = zipfile.ZipInfo(name)
            if name == "game_now.sqlite3":
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            out.writestr(info, original.read(name))
    with pytest.raises(BackupError, match="Unsafe ZIP"):
        restore_backup(symlink_archive, tmp_path / "link.sqlite3")


def test_incompatible_sqlite_not_exported(tmp_path: Path):
    source = tmp_path / "not-game-now.sqlite3"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE example(id INTEGER)")
    with pytest.raises(BackupError, match="compatible"):
        create_backup(source, tmp_path / "backup.zip")


def test_log_restore_cannot_overwrite_existing_log(tmp_path: Path):
    source = tmp_path / "db.sqlite3"
    sample_db(source)
    logfile = tmp_path / "game_now.log"
    logfile.write_text("private log")
    backup = tmp_path / "backup.zip"
    create_backup(source, backup, include_logs=True, log_file=logfile)
    logs_dest = tmp_path / "restorelogs"
    logs_dest.mkdir()
    (logs_dest / "game_now.log").write_text("existing")
    with pytest.raises(BackupError, match="Log destination exists"):
        restore_backup(backup, tmp_path / "restore.sqlite3", logs_directory=logs_dest)
    assert not (tmp_path / "restore.sqlite3").exists()
    assert (logs_dest / "game_now.log").read_text() == "existing"


def test_cli_backup_and_restore_emit_metadata_only(tmp_path: Path, capsys):
    original = tmp_path / "game.sqlite3"
    sample_db(original)
    backup = tmp_path / "backup.zip"
    assert main(["backup", "--db", str(original), "--output", str(backup)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["result"] == "backup_created"
    assert not any(key in result for key in ("media", "player_id", "text"))
    restored = tmp_path / "restored.sqlite3"
    assert main(["restore", "--db", str(restored), "--archive", str(backup)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["result"] == "backup_restored"
    assert SQLiteStore(restored).get_match("match-092").home.name == "Azul"
