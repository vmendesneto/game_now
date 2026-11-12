"""Read-only reanalysis of retained text; never reconstructs unrecorded UI choices."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.contracts import AudioSource, Match
from app.narration_tracking import track_narration

MAX_ARCHIVE_BYTES = 8_000_000


def archive_path(root: Path, match_id: str) -> Path:
    path = root / (hashlib.sha256(match_id.encode()).hexdigest() + ".json")
    if path.resolve().parent != root.resolve():
        raise ValueError("Invalid archive path")
    return path


def load_saved_diagnostics(root: Path, match: Match, sources: list[AudioSource]) -> dict:
    path = archive_path(root, match.id)
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive too large")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("match_id") != match.id or not isinstance(report.get("windows"), list) or len(report["windows"]) > 200:
        raise ValueError("Invalid archive")
    Match.model_validate(report["match"])
    allowed = {source.id for source in sources}
    report["windows"] = [row for row in report["windows"] if row["source_id"] in allowed]
    current = hashlib.sha256(json.dumps(match.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    return {**report, "saved_report": True, "current_context_matches": current == report.get("context_fingerprint")}


def diagnose_actions(match: Match, snapshot: dict, sources: list[AudioSource], capture: dict) -> dict:
    allowed = {source.id: source.name for source in sources}
    streams = capture.get("streams", [capture])
    starts = {row["source_id"]: row.get("requested_start_seconds") for row in streams if row.get("source_id")}
    windows = []
    for entry in snapshot.get("entries", [])[-200:]:
        if entry["source_id"] not in allowed:
            continue
        start, end = entry["start_seconds"], entry["end_seconds"]
        offset = starts.get(entry["source_id"])
        windows.append({"source_id": entry["source_id"], "source_name": allowed[entry["source_id"]],
            "sequence": entry["sequence"], "audio_start_seconds": start, "audio_end_seconds": end,
            "requested_video_start_seconds": start+offset if offset is not None else None,
            "requested_video_end_seconds": end+offset if offset is not None else None,
            "text": entry["text"], "captured_at": entry["captured_at"], "processed_at": entry["processed_at"],
            "actions": track_narration(match, entry["text"])})
    context = match.model_dump(mode="json")
    return {"match_id": match.id, "match": context, "windows": windows,
            "context_fingerprint": hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest(),
            "basis": "reanalysis_of_retained_text_with_current_roster",
            "original_context_verified": False, "runtime_selection_reconstructed": False,
            "video_seek_verified": False, "audio_retransmitted": False, "persisted": False,
            "accuracy_measured": False}
