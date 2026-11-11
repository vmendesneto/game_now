"""GN-050: labeled synthetic corpus and conservative feed-level gating."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from app.asr_windows import WindowTranscript
from app.narration_classifier import NarrationKind, classify_narration
from app.transcription_feed import TranscriptFeed


CORPUS = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "narration_corpus_v1.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("sample", CORPUS["samples"], ids=lambda sample: sample["id"])
def test_labeled_synthetic_corpus(sample):
    result = classify_narration(sample["text"])
    assert result.kind.value == sample["label"]
    assert result.eligible_for_live_state == (sample["label"] == "live_play")
    assert result.reason


def test_corpus_labels_unique_and_all_classes_covered():
    assert CORPUS["source"] == "synthetic_handwritten_pt_BR"
    assert len({sample["id"] for sample in CORPUS["samples"]}) == len(CORPUS["samples"])
    counts = Counter(sample["label"] for sample in CORPUS["samples"])
    assert set(counts) == {kind.value for kind in NarrationKind}
    assert min(counts.values()) >= 8


@pytest.mark.parametrize("text,kind", [
    ("GOL DO VERMELHO! Patrocínio da Loja X.", NarrationKind.AD),
    ("Bola na área. Replay do lance de ontem.", NarrationKind.REPLAY),
    ("O chute foi bom. Na minha opinião a defesa falhou.", NarrationKind.ANALYSIS),
    ("Manda um abraço. Gol para o torcedor!", NarrationKind.CONVERSATION),
    ("BOLA", NarrationKind.UNKNOWN),
    ("desgolaçoado", NarrationKind.UNKNOWN),
    ("", NarrationKind.UNKNOWN),
    ("   \n\t  ", NarrationKind.UNKNOWN),
])
def test_mixed_or_ambiguous_segments_cannot_update_live_state(text, kind):
    result = classify_narration(text)
    assert result.kind == kind
    assert not result.eligible_for_live_state


def test_non_string_rejected_and_json_safe_reason():
    with pytest.raises(TypeError):
        classify_narration(None)  # type: ignore[arg-type]
    decision = classify_narration("https://example.com/?token=secret")
    assert decision.kind == NarrationKind.UNKNOWN
    assert "secret" not in json.dumps(decision.as_dict())


def test_text_feed_adds_label_without_mutating_text_or_other_sources():
    feed = TranscriptFeed(max_sources_per_match=2)
    now = datetime.now(timezone.utc)

    def update(source: str, text: str) -> WindowTranscript:
        return WindowTranscript(
            source_id=source, sequence=0, start_seconds=0, end_seconds=6,
            language="pt", raw_text=text, new_text=text,
        )

    feed.publish("match", "radio", update("radio", "Gol do Azul!"), captured_at=now)
    feed.publish("match", "youtube", update("youtube", "Replay do gol do Azul!"), captured_at=now)
    entries = {entry["source_id"]: entry for entry in feed.snapshot("match")["entries"]}
    assert entries["radio"]["text"] == "Gol do Azul!"
    assert entries["radio"]["narration_kind"] == "live_play"
    assert entries["radio"]["eligible_for_live_state"] is True
    assert entries["youtube"]["narration_kind"] == "replay"
    assert entries["youtube"]["eligible_for_live_state"] is False
    assert entries["radio"]["classification_reason"] == "explicit_live_cue"
    assert entries["youtube"]["classification_reason"] == "replay_cue"
    assert entries["radio"]["captured_at"] == now.isoformat()
    assert "url" not in entries["radio"]
