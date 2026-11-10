"""Persisted match-management rules (GN-024), independent of ContractBundle v1."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator

from app.contracts import ContractBundle, Id, Match, NonNegativeSeconds, StrictModel
from app.storage import SQLiteStore, StoreConflict


ActionKind = Literal["substitution", "red_card", "half_time", "second_half", "added_time", "finish"]


class MatchAction(StrictModel):
    kind: ActionKind
    player_out_id: Id | None = None
    player_in_id: Id | None = None
    player_id: Id | None = None
    seconds: int | None = Field(default=None, ge=0, le=3600)
    match_seconds: NonNegativeSeconds | None = None

    @model_validator(mode="after")
    def check_fields(self) -> "MatchAction":
        required = {
            "substitution": {"player_out_id", "player_in_id"},
            "red_card": {"player_id"},
            "added_time": {"seconds"},
        }.get(self.kind, set())
        provided = {
            name for name in ("player_out_id", "player_in_id", "player_id", "seconds")
            if getattr(self, name) is not None
        }
        if provided != required:
            raise ValueError(f"{self.kind} requires exactly: {', '.join(sorted(required)) or 'no action fields'}")
        if self.kind == "substitution" and self.player_out_id == self.player_in_id:
            raise ValueError("Outgoing and incoming players must differ")
        return self


def empty_flow() -> dict:
    return {"substitutions": [], "sent_off_ids": [],
            "added_time_seconds": {"first_half": 0, "second_half": 0},
            "operations": []}


def on_pitch(match: Match, flow: dict) -> set[str]:
    """Initial starters minus substitutions and expulsions (no speculative lineup)."""
    active = {player.id for player in match.players if player.starter}
    for pair in flow["substitutions"]:
        active.discard(pair["out"])
        active.add(pair["in"])
    active.difference_update(flow["sent_off_ids"])
    return active


def flow_view(match: Match, flow: dict) -> dict:
    return {
        **flow,
        "period": match.period,
        "match_seconds": match.match_seconds,
        "home_attack_direction": match.home.attack_direction,
        "away_attack_direction": match.away.attack_direction,
        "active_player_ids": sorted(on_pitch(match, flow)),
    }


class MatchFlowService:
    """Single SQLite transaction updates match, canonical snapshot and action history."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def get(self, match_id: str) -> dict | None:
        with self.store._connect() as conn:
            match = self.store._get_match(conn, match_id)
            if match is None:
                return None
            row = conn.execute("SELECT payload FROM match_flow WHERE match_id=?", (match_id,)).fetchone()
            import json
            return flow_view(match, json.loads(row[0]) if row else empty_flow())

    def apply(self, match_id: str, action: MatchAction) -> dict | None:
        import json
        with self.store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            match = self.store._get_match(conn, match_id)
            if match is None:
                return None
            row = conn.execute("SELECT payload FROM match_flow WHERE match_id=?", (match_id,)).fetchone()
            flow = json.loads(row[0]) if row else empty_flow()
            if action.match_seconds is not None and action.match_seconds < match.match_seconds:
                raise StoreConflict("Match clock cannot move backwards")
            changes = match.model_dump(mode="json")
            if action.match_seconds is not None:
                changes["match_seconds"] = action.match_seconds
            active = on_pitch(match, flow)
            players = {player.id: player for player in match.players}
            if action.kind == "substitution":
                if match.period not in ("first_half", "half_time", "second_half"):
                    raise StoreConflict("Substitutions are not allowed after full time")
                outgoing = players.get(action.player_out_id)
                incoming = players.get(action.player_in_id)
                if outgoing is None or incoming is None or outgoing.team_id != incoming.team_id:
                    raise StoreConflict("Substitutions require two players on the same team")
                used = {pair["out"] for pair in flow["substitutions"]}
                if (outgoing.id not in active or incoming.id in active
                        or incoming.id in used or incoming.id in flow["sent_off_ids"]):
                    raise StoreConflict("Outgoing player must be active and incoming player must be eligible")
                flow["substitutions"].append({
                    "out": outgoing.id, "in": incoming.id, "team_id": outgoing.team_id,
                    "period": match.period,
                })
            elif action.kind == "red_card":
                if match.period not in ("first_half", "second_half"):
                    raise StoreConflict("Red cards require active play")
                if action.player_id not in active:
                    raise StoreConflict("Only an on-pitch player can be sent off")
                flow["sent_off_ids"].append(action.player_id)
            elif action.kind == "half_time":
                if match.period != "first_half":
                    raise StoreConflict("Half-time can only follow the first half")
                changes["period"] = "half_time"
            elif action.kind == "second_half":
                if match.period != "half_time":
                    raise StoreConflict("Second half requires half-time first")
                changes["period"] = "second_half"
                for side in ("home", "away"):
                    direction = changes[side]["attack_direction"]
                    changes[side]["attack_direction"] = (
                        "right_to_left" if direction == "left_to_right" else "left_to_right"
                    )
            elif action.kind == "added_time":
                if match.period not in ("first_half", "second_half"):
                    raise StoreConflict("Added time applies only to a playing half")
                previous = flow["added_time_seconds"][match.period]
                if action.seconds < previous:
                    raise StoreConflict("Added time cannot decrease")
                flow["added_time_seconds"][match.period] = action.seconds
            elif action.kind == "finish":
                if match.period != "second_half":
                    raise StoreConflict("Full time can only follow the second half")
                changes["period"] = "finished"

            updated = Match.model_validate(changes)
            before = self.store._get_state(conn, match_id)
            assert before is not None
            snapshot_data = before.model_dump(mode="json")
            snapshot_data["match"] = updated.model_dump(mode="json")
            # A retired player or interval is not evidence of possession or ball location.
            clear = action.kind in ("half_time", "second_half", "finish")
            affected = {action.player_out_id, action.player_id} - {None}
            if clear or snapshot_data["ball"]["player_id"] in affected:
                ball = snapshot_data["ball"]
                ball.update(team_id=None, player_id=None, zone=None, uncertainty="uncertain",
                            updated_at=datetime.now(timezone.utc).isoformat(), expires_at=None)
            snapshot = ContractBundle.model_validate(snapshot_data)
            now = datetime.now(timezone.utc).isoformat()
            flow["operations"].append({
                "id": "op-" + uuid4().hex, "recorded_at": now,
                "kind": action.kind, "match_seconds": updated.match_seconds,
                "details": action.model_dump(mode="json", exclude_none=True),
            })
            conn.execute("UPDATE matches SET payload=?,updated_at=? WHERE id=?",
                         (updated.model_dump_json(), now, match_id))
            conn.execute("UPDATE snapshots SET payload=? WHERE match_id=?",
                         (snapshot.model_dump_json(), match_id))
            conn.execute(
                "INSERT INTO match_flow (match_id, payload) VALUES (?, ?) "
                "ON CONFLICT(match_id) DO UPDATE SET payload=excluded.payload",
                (match_id, json.dumps(flow, ensure_ascii=False)),
            )
            return flow_view(updated, flow)
