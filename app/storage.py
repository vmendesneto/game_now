"""SQLite configuration and state store; no media is stored or served."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator

from pydantic import ValidationError

from app.configuration import MatchConfig, RosterPlayer
from app.contracts import AudioSource, ContractBundle, EstimatedBallState, Match, Player


DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "game_now.sqlite3"


class StoreConflict(Exception):
    """An operation would violate a persisted match or event reference."""


class SQLiteStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("GAME_NOW_DB_PATH", DEFAULT_DB))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS matches (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS roster_positions (
                    match_id TEXT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
                    player_id TEXT NOT NULL,
                    position TEXT NOT NULL,
                    PRIMARY KEY(match_id, player_id)
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    match_id TEXT PRIMARY KEY REFERENCES matches(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS match_flow (
                    match_id TEXT PRIMARY KEY REFERENCES matches(id) ON DELETE CASCADE,
                    payload TEXT NOT NULL
                );
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _get_match(conn: sqlite3.Connection, match_id: str) -> Match | None:
        row = conn.execute("SELECT payload FROM matches WHERE id=?", (match_id,)).fetchone()
        return Match.model_validate_json(row[0]) if row else None

    @staticmethod
    def _get_state(conn: sqlite3.Connection, match_id: str) -> ContractBundle | None:
        row = conn.execute("SELECT payload FROM snapshots WHERE match_id=?", (match_id,)).fetchone()
        return ContractBundle.model_validate_json(row[0]) if row else None

    @staticmethod
    def _checked_bundle(snapshot: ContractBundle, match: Match | None = None,
                        sources: list[AudioSource] | None = None) -> ContractBundle:
        data = snapshot.model_dump(mode="json")
        if match is not None:
            data["match"] = match.model_dump(mode="json")
        if sources is not None:
            data["sources"] = [source.model_dump(mode="json") for source in sources]
        try:
            return ContractBundle.model_validate(data)
        except ValidationError as exc:
            raise StoreConflict("Existing events or ball state reference removed entities") from exc

    def list_matches(self) -> list[Match]:
        with self._connect() as conn:
            rows = conn.execute("SELECT payload FROM matches ORDER BY created_at, id").fetchall()
            return [Match.model_validate_json(row[0]) for row in rows]

    def get_match(self, match_id: str) -> Match | None:
        with self._connect() as conn:
            return self._get_match(conn, match_id)

    def create_match(self, config: MatchConfig) -> Match:
        match = Match.model_validate(config.model_dump())
        initial = ContractBundle(match=match, ball=EstimatedBallState(updated_at=datetime.now(timezone.utc)))
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            try:
                conn.execute("INSERT INTO matches VALUES (?, ?, ?, ?)",
                             (match.id, match.model_dump_json(), now, now))
                conn.execute("INSERT INTO snapshots VALUES (?, ?)",
                             (match.id, initial.model_dump_json()))
            except sqlite3.IntegrityError as exc:
                raise StoreConflict("Match ID already exists") from exc
        return match

    def update_match(self, match_id: str, config: MatchConfig) -> Match | None:
        if match_id != config.id:
            raise StoreConflict("URL match ID and body ID differ")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            old = self._get_match(conn, match_id)
            if old is None:
                return None
            if old.players and (old.home.id != config.home.id or old.away.id != config.away.id):
                raise StoreConflict("Cannot replace team IDs while rosters exist")
            new_match = Match.model_validate({**config.model_dump(),
                                              "players": [p.model_dump() for p in old.players]})
            flow_row = conn.execute(
                "SELECT payload FROM match_flow WHERE match_id=?", (match_id,)
            ).fetchone()
            if flow_row and json.loads(flow_row[0]).get("operations"):
                if (new_match.period != old.period
                        or new_match.home.attack_direction != old.home.attack_direction
                        or new_match.away.attack_direction != old.away.attack_direction
                        or new_match.match_seconds < old.match_seconds):
                    raise StoreConflict("Use match actions to advance period, directions and clock")
            old_state = self._get_state(conn, match_id)
            assert old_state is not None
            new_state = self._checked_bundle(old_state, match=new_match)
            conn.execute("UPDATE matches SET payload=?, updated_at=? WHERE id=?",
                         (new_match.model_dump_json(), datetime.now(timezone.utc).isoformat(), match_id))
            conn.execute("UPDATE snapshots SET payload=? WHERE match_id=?",
                         (new_state.model_dump_json(), match_id))
            return new_match

    def delete_match(self, match_id: str) -> bool:
        with self._connect() as conn:
            return conn.execute("DELETE FROM matches WHERE id=?", (match_id,)).rowcount > 0

    def get_roster(self, match_id: str) -> list[RosterPlayer] | None:
        with self._connect() as conn:
            match = self._get_match(conn, match_id)
            if match is None:
                return None
            positions = dict(conn.execute(
                "SELECT player_id, position FROM roster_positions WHERE match_id=?", (match_id,)
            ).fetchall())
            return [RosterPlayer.model_validate({**player.model_dump(),
                                                  "position": positions.get(player.id, "other")})
                    for player in match.players]

    def replace_roster(self, match_id: str, roster: list[RosterPlayer]) -> list[RosterPlayer] | None:
        numbers: set[tuple[str, int]] = set()
        starters: dict[str, int] = {}
        for player in roster:
            shirt = (player.team_id, player.number)
            if shirt in numbers:
                raise StoreConflict("Shirt number must be unique within each team")
            numbers.add(shirt)
            if player.starter:
                starters[player.team_id] = starters.get(player.team_id, 0) + 1
                if starters[player.team_id] > 11:
                    raise StoreConflict("A team cannot have more than 11 starters")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            match = self._get_match(conn, match_id)
            if match is None:
                return None
            try:
                updated = Match.model_validate({
                    **match.model_dump(mode="json"),
                    "players": [p.model_dump(exclude={"position"}) for p in roster],
                })
            except ValidationError as exc:
                raise StoreConflict("Invalid roster: unknown team or duplicate player ID") from exc
            flow_row = conn.execute(
                "SELECT payload FROM match_flow WHERE match_id=?", (match_id,)
            ).fetchone()
            if (flow_row and json.loads(flow_row[0]).get("operations")
                    and updated.players != match.players):
                raise StoreConflict("Roster is locked after match actions; player identities must remain stable")
            existing = self._get_state(conn, match_id)
            assert existing is not None
            snapshot = self._checked_bundle(existing, match=updated)
            conn.execute("UPDATE matches SET payload=?, updated_at=? WHERE id=?",
                         (updated.model_dump_json(), datetime.now(timezone.utc).isoformat(), match_id))
            conn.execute("DELETE FROM roster_positions WHERE match_id=?", (match_id,))
            conn.executemany("INSERT INTO roster_positions VALUES (?, ?, ?)",
                             [(match_id, p.id, p.position) for p in roster])
            conn.execute("UPDATE snapshots SET payload=? WHERE match_id=?",
                         (snapshot.model_dump_json(), match_id))
            return roster

    def get_state(self, match_id: str) -> ContractBundle | None:
        with self._connect() as conn:
            return self._get_state(conn, match_id)

    def replace_state(self, match_id: str, bundle: ContractBundle) -> ContractBundle | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            match = self._get_match(conn, match_id)
            if match is None:
                return None
            if bundle.match.id != match_id or bundle.match != match:
                raise StoreConflict("State must use the saved match and roster; edit them through their APIs")
            conn.execute("UPDATE snapshots SET payload=? WHERE match_id=?",
                         (bundle.model_dump_json(), match_id))
            return bundle

    def get_sources(self, match_id: str) -> list[AudioSource] | None:
        state = self.get_state(match_id)
        return state.sources if state else None

    def replace_sources(self, match_id: str, sources: list[AudioSource]) -> list[AudioSource] | None:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            state = self._get_state(conn, match_id)
            if state is None:
                return None
            bundle = self._checked_bundle(state, sources=sources)
            conn.execute("UPDATE snapshots SET payload=? WHERE match_id=?",
                         (bundle.model_dump_json(), match_id))
            return sources
