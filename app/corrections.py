"""GN-025 audited manual corrections; never rewrite evidence without an audit row."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, ValidationError, model_validator

from app.contracts import ContractBundle, Id, Match, StrictModel
from app.storage import SQLiteStore, StoreConflict


class ManualCorrection(StrictModel):
    kind: Literal["score", "possession", "event"]
    reason: str = Field(min_length=5, max_length=400)
    actor: str = Field(default="operator", min_length=1, max_length=80)
    home_score: int | None = Field(default=None, ge=0)
    away_score: int | None = Field(default=None, ge=0)
    team_id: Id | None = None
    player_id: Id | None = None
    event_id: Id | None = None
    changes: dict[str, Any] | None = None

    @model_validator(mode="after")
    def verify_shape(self) -> "ManualCorrection":
        supplied = set(self.model_fields_set) - {"kind", "reason", "actor"}
        if self.kind == "score":
            if supplied != {"home_score", "away_score"}:
                raise ValueError("Score correction requires home_score and away_score")
        elif self.kind == "possession":
            if "team_id" not in supplied or not supplied <= {"team_id", "player_id"}:
                raise ValueError("Possession correction requires team_id (null if unknown)")
            if self.player_id is not None and self.team_id is None:
                raise ValueError("Possession player requires a team")
        elif self.kind == "event":
            if supplied != {"event_id", "changes"} or not self.changes:
                raise ValueError("Event correction requires event_id and changes")
            permitted = {"kind", "team_id", "player_id", "zone", "uncertainty", "match_seconds"}
            if not set(self.changes) <= permitted:
                raise ValueError("Event identity, provenance and timestamps cannot be edited")
        return self


def write_audit(conn, match_id: str, *, kind: str, reason: str,
                actor: str, before: dict, after: dict) -> dict:
    audit = {
        "id": "cor-" + uuid4().hex, "match_id": match_id,
        "kind": kind, "reason": reason, "actor": actor,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "before": before, "after": after,
    }
    conn.execute("INSERT INTO match_corrections (id,match_id,payload) VALUES (?,?,?)",
                 (audit["id"], match_id, json.dumps(audit, ensure_ascii=False)))
    return audit


class CorrectionService:
    def __init__(self, store: SQLiteStore):
        self.store = store

    def list(self, match_id: str) -> list[dict] | None:
        with self.store._connect() as conn:
            if self.store._get_match(conn, match_id) is None:
                return None
            rows = conn.execute(
                "SELECT payload FROM match_corrections WHERE match_id=? ORDER BY rowid",
                (match_id,),
            ).fetchall()
            return [json.loads(row[0]) for row in rows]

    def apply(self, match_id: str, correction: ManualCorrection) -> dict | None:
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            match = self.store._get_match(conn, match_id)
            if match is None:
                return None
            current = self.store._get_state(conn, match_id)
            assert current is not None
            before = current.model_dump(mode="json")
            changed = current.model_dump(mode="json")
            if correction.kind == "score":
                changed["match"]["home_score"] = correction.home_score
                changed["match"]["away_score"] = correction.away_score
            elif correction.kind == "possession":
                team_id = correction.team_id
                player_id = correction.player_id
                teams = {match.home.id, match.away.id}
                if team_id is not None and team_id not in teams:
                    raise StoreConflict("Unknown possession team")
                players = {p.id: p for p in match.players}
                if player_id is not None and (
                    player_id not in players or players[player_id].team_id != team_id
                ):
                    raise StoreConflict("Possession player does not belong to team")
                changed["ball"].update({
                    "team_id": team_id, "player_id": player_id,
                    "last_event_id": None, "zone": None,
                    "confidences": {}, "uncertainty": "uncertain",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "expires_at": None,
                })
            elif correction.kind == "event":
                target = next(
                    (event for event in changed["events"] if event["id"] == correction.event_id),
                    None,
                )
                if target is None:
                    raise StoreConflict("Event not found")
                target.update(correction.changes)
                if changed["ball"]["last_event_id"] == correction.event_id:
                    changed["ball"].update({
                        "last_event_id": None, "team_id": None, "player_id": None,
                        "zone": None, "confidences": {}, "uncertainty": "uncertain",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "expires_at": None,
                    })
            try:
                updated = ContractBundle.model_validate(changed)
            except ValidationError as exc:
                raise StoreConflict("Correction conflicts with persisted event references") from exc
            after = updated.model_dump(mode="json")
            if before == after:
                raise StoreConflict("Correction does not change persisted state")
            if correction.kind == "score":
                conn.execute(
                    "UPDATE matches SET payload=?,updated_at=? WHERE id=?",
                    (updated.match.model_dump_json(), datetime.now(timezone.utc).isoformat(), match_id),
                )
            conn.execute("UPDATE snapshots SET payload=? WHERE match_id=?",
                         (updated.model_dump_json(), match_id))
            return write_audit(
                conn, match_id, kind=correction.kind,
                reason=correction.reason.strip(), actor=correction.actor.strip(),
                before=before, after=after,
            )
