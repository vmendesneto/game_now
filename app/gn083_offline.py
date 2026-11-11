"""GN-083: bounded local-audio transcription and read-only narration evidence.

Capture/decoding success is not proof of ASR accuracy. Real metrics require a
separately annotated permitted sample; this module never invents them.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import re
import unicodedata
import wave

from app.asr import BYTES_PER_SECOND, SAMPLE_RATE

MAX_SECONDS = 600
MAX_ROWS = 3000
FIELDS = ("team_id", "player_id", "zone", "event_kind", "narration_kind")


def pcm_chunks(path: Path, *, raw: bool = False, max_seconds: int = MAX_SECONDS) -> Iterator[bytes]:
    """Stream half-second PCM chunks without uploading or retaining the recording."""
    if not 1 <= max_seconds <= MAX_SECONDS:
        raise ValueError("max_seconds must be between 1 and 600")
    if not path.is_file():
        raise ValueError("Local audio file not found")
    if raw:
        size = path.stat().st_size
        if not size or size % 2 or size > max_seconds * BYTES_PER_SECOND:
            raise ValueError("Raw PCM must be aligned, nonempty and within duration limit")
        with path.open("rb") as stream:
            while block := stream.read(BYTES_PER_SECOND // 2):
                yield block
    else:
        try:
            with wave.open(str(path), "rb") as stream:
                if (stream.getnchannels() != 1 or stream.getsampwidth() != 2
                        or stream.getframerate() != SAMPLE_RATE or stream.getcomptype() != "NONE"):
                    raise ValueError("WAV must be PCM mono s16le 16000 Hz")
                if not stream.getnframes() or stream.getnframes() > max_seconds * SAMPLE_RATE:
                    raise ValueError("WAV duration exceeds limit or is empty")
                while block := stream.readframes(SAMPLE_RATE // 2):
                    yield block
        except (EOFError, OSError, wave.Error) as exc:
            raise ValueError("Invalid or unreadable local WAV") from exc


def transcribe_file(path: Path, match, *, raw: bool = False, source_id: str = "audio-local",
                    model: str = "tiny", max_seconds: int = MAX_SECONDS,
                    transcriber=None) -> list[dict]:
    """Run the existing CPU ASR and overlap deduplicator on a local file only."""
    from app.asr import ASRSettings, CPUTranscriber
    from app.asr_vocabulary import build_vocabulary_prompt
    from app.asr_windows import RollingASRProcessor, WindowSettings

    engine = transcriber or CPUTranscriber(ASRSettings(
        model=model, max_seconds=60, initial_prompt=build_vocabulary_prompt(match),
    ))
    processor = RollingASRProcessor(engine, WindowSettings())
    observations: list[dict] = []

    def collect(updates) -> None:
        for update in updates:
            if update.new_text.strip():
                observations.append({
                    "source_id": update.source_id, "sequence": update.sequence,
                    "start_seconds": update.start_seconds,
                    "end_seconds": update.end_seconds, "text": update.new_text,
                })

    for chunk in pcm_chunks(path, raw=raw, max_seconds=max_seconds):
        collect(processor.push(source_id, chunk))
    collect(processor.finish(source_id))
    return observations


def validate_observations(rows: object) -> list[dict]:
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise ValueError("Observations must be an array with at most 3000 entries")
    result = []
    last: dict[str, tuple[int, float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Observation must be an object")
        source, seq = row.get("source_id"), row.get("sequence")
        start, end, value = row.get("start_seconds"), row.get("end_seconds"), row.get("text")
        if (not isinstance(source, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", source)
                or type(seq) is not int or seq < 0
                or type(start) not in (int, float) or type(end) not in (int, float)
                or not 0 <= start <= end <= MAX_SECONDS
                or not isinstance(value, str) or not value.strip() or len(value) > 2048):
            raise ValueError("Invalid observation source, sequence, times or text")
        if source in last and (seq <= last[source][0] or start < last[source][1]):
            raise ValueError("Observation times/sequences must advance per source")
        last[source] = (seq, float(start))
        result.append({"source_id": source, "sequence": seq, "start_seconds": float(start),
                       "end_seconds": float(end), "text": value.strip()})
    return result


def analyze_observations(match, rows: object, *, include_text: bool = False) -> list[dict]:
    """Independent, abstaining diagnostics: no state or score updates."""
    from app.event_detection import EventRequest, detect_event
    from app.field_regions import RegionRequest, detect_region
    from app.narration_classifier import classify_narration
    from app.narration_entities import NarrationResolveRequest, resolve_narration
    from app.possession import PossessionRequest, detect_possession

    results = []
    for row in validate_observations(rows):
        phrase = row["text"]
        category = classify_narration(phrase)
        entity = resolve_narration(match, NarrationResolveRequest(text=phrase))
        possession = detect_possession(match, PossessionRequest(text=phrase))
        region = detect_region(match, RegionRequest(
            text=phrase, team_id=possession.team_id if possession.status == "explicit" else None,
        ))
        event = detect_event(match, EventRequest(text=phrase))
        team = player = evidence = None
        if entity.eligible_for_live_state and match.period in ("first_half", "second_half"):
            ambiguous = any(m.status != "resolved" for m in entity.mentions
                            if m.kind in ("team", "player", "pronoun", "unknown"))
            teams = {m.team_id for m in entity.mentions if m.team_id is not None}
            players = {m.player_id for m in entity.mentions if m.player_id is not None}
            if not ambiguous and len(teams) == 1:
                team, evidence = next(iter(teams)), "mention"
            if not ambiguous and len(players) == 1:
                player = next(iter(players))
            if possession.status == "explicit":
                team, evidence = possession.team_id, "possession"
                if possession.player_id is not None:
                    player = possession.player_id
            if player and team and next(
                    (p.team_id for p in match.players if p.id == player), None) != team:
                player = None
        prediction = {
            "source_id": row["source_id"], "sequence": row["sequence"],
            "start_seconds": row["start_seconds"], "end_seconds": row["end_seconds"],
            "narration_kind": category.label.value,
            "team_id": team, "team_evidence": evidence, "player_id": player,
            "possession_team_id": possession.team_id if possession.status == "explicit" else None,
            "zone": region.zone.model_dump(mode="json") if region.status == "explicit" else None,
            "event_kind": event.kind.value if event.status == "explicit" else None,
            "reasons": {"possession": possession.reason, "region": region.reason,
                        "event": event.reason},
            "state_updated": False,
        }
        if include_text:
            prediction["text"] = phrase
        results.append(prediction)
    return results


def _words(value: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return re.findall(r"[a-z0-9]+", "".join(c for c in folded if not unicodedata.combining(c)))


def _distance(first: list[str], second: list[str]) -> int:
    previous = list(range(len(second) + 1))
    for i, word in enumerate(first, 1):
        current = [i]
        for j, other in enumerate(second, 1):
            current.append(min(previous[j] + 1, current[-1] + 1,
                               previous[j - 1] + (word != other)))
        previous = current
    return previous[-1]


def evaluate(predictions: list[dict], reference: object, *, tolerance_seconds: float = 2.) -> dict:
    """Temporal, label-independent 1:1 match of independently annotated intervals.

    Unmatched predictions are explicitly reported and cannot boost precision.
    A null reference value is an annotated negative, unlike an omitted field.
    """
    if not isinstance(reference, list) or not reference or len(reference) > MAX_ROWS:
        raise ValueError("Reference must be a nonempty array with <=3000 entries")
    if not 0 <= tolerance_seconds <= 10:
        raise ValueError("Invalid time alignment tolerance")
    for item in reference:
        if not isinstance(item, dict) or not any(key in item for key in FIELDS):
            raise ValueError("Reference needs at least one explicitly annotated label")
        start, end = item.get("start_seconds"), item.get("end_seconds")
        if (not isinstance(item.get("source_id"), str)
                or type(start) not in (int, float) or type(end) not in (int, float)
                or not 0 <= start <= end <= MAX_SECONDS):
            raise ValueError("Reference needs a source and bounded time interval")
        for key in FIELDS:
            if key not in item or item[key] is None:
                continue
            value = item[key]
            if key == "zone":
                if (not isinstance(value, dict) or set(value) != {"band", "lane"}
                        or type(value["band"]) is not int or value["band"] not in range(1, 6)
                        or value["lane"] not in ("left", "center", "right")):
                    raise ValueError("Invalid reference zone")
            elif not isinstance(value, str) or not value:
                raise ValueError("Invalid reference label")
        if "reference_text" in item and not isinstance(item["reference_text"], str):
            raise ValueError("Invalid reference_text")

    candidates = []
    for i, gold in enumerate(reference):
        for j, pred in enumerate(predictions):
            if gold["source_id"] != pred["source_id"]:
                continue
            gap = max(0., max(gold["start_seconds"], pred["start_seconds"])
                      - min(gold["end_seconds"], pred["end_seconds"]))
            if gap <= tolerance_seconds:
                midpoint_gold = (gold["start_seconds"] + gold["end_seconds"]) / 2
                midpoint_pred = (pred["start_seconds"] + pred["end_seconds"]) / 2
                candidates.append((abs(midpoint_gold - midpoint_pred), gap, i, j))
    assigned: dict[int, dict] = {}
    used_predictions: set[int] = set()
    for _, _, i, j in sorted(candidates):
        if i not in assigned and j not in used_predictions:
            assigned[i] = predictions[j]
            used_predictions.add(j)
    metrics = {}
    for field in FIELDS:
        annotated = support = predicted = correct = fp = fn = 0
        for i, gold in enumerate(reference):
            if field not in gold:
                continue
            annotated += 1
            actual, found = gold[field], assigned.get(i, {}).get(field)
            support += actual is not None
            predicted += found is not None
            correct += found is not None and found == actual
            if found != actual:
                fp += found is not None
                fn += actual is not None
        metrics[field] = {
            "annotated": annotated, "reference_positives": support,
            "predicted_positives": predicted, "correct": correct,
            "false_positives": fp, "false_negatives": fn,
            "precision": round(correct / (correct + fp), 4) if correct + fp else None,
            "recall": round(correct / support, 4) if support else None,
            "coverage": round(predicted / annotated, 4) if annotated else None,
        }
    word_count = word_errors = 0
    for i, gold in enumerate(reference):
        if "reference_text" in gold:
            expected = _words(gold["reference_text"])
            predicted_text = _words(assigned.get(i, {}).get("text", ""))
            word_errors += _distance(expected, predicted_text)
            word_count += len(expected)
    return {
        "evidence": "reference_comparison",
        "reference_segments": len(reference), "aligned_segments": len(assigned),
        "unmatched_predictions": len(predictions) - len(used_predictions),
        "unmatched_reference": len(reference) - len(assigned),
        "metrics": metrics,
        "word_error_rate": round(word_errors / word_count, 4) if word_count else None,
        "wer_reference_words": word_count,
        "warning": "Heuristic temporal matching; metrics are not calibrated confidence",
    }
