"""GN-035: deterministic source telemetry; no external media or Windows claims."""
from datetime import datetime, timedelta, timezone
import pytest
from app.source_telemetry import SourceTelemetry


def test_pcm_heartbeat_expiry_content_and_delay_are_conservative():
    tick = [100.0]
    timestamp = datetime(2026, 11, 11, 19, 0, tzinfo=timezone.utc)
    telemetry = SourceTelemetry(clock=lambda: tick[0], utcnow=lambda: timestamp,
                                stale_seconds=8, content_ttl_seconds=20)
    assert telemetry.snapshot("match", "source")["signal"] == "unobserved"
    telemetry.observe_text("match", "source", "ad", captured_at=timestamp,
                           processed_at=timestamp+timedelta(seconds=1))
    assert telemetry.snapshot("match", "source")["content"] == "unknown"
    assert telemetry.observe_pcm("match", "source", 32000)
    assert not telemetry.observe_pcm("match", "source", 32000)
    value = telemetry.snapshot("match", "source")
    assert value["signal"] == "online"
    assert value["content"] == "commercial"
    assert value["processing_delay_seconds"] == 1.0
    assert value["relative_delay_seconds"] is None
    tick[0] += 9
    assert telemetry.snapshot("match", "source")["signal"] == "no_audio"
    assert telemetry.snapshot("match", "source")["content"] == "unknown"
    assert telemetry.observe_pcm("match", "source", 16000)
    telemetry.observe_text("match", "source", "live_play", captured_at=timestamp,
                           processed_at=timestamp+timedelta(seconds=2))
    assert telemetry.snapshot("match", "source")["content"] == "narrating"
    tick[0] += 21
    assert telemetry.snapshot("match", "source")["content"] == "unknown"
    telemetry.stop("match", "source")
    assert telemetry.snapshot("match", "source")["signal"] == "stopped"
    telemetry.clear_match("match")
    assert telemetry.snapshot("match", "source")["signal"] == "unobserved"


def test_zero_length_pcm_unknown_delay_and_isolation():
    tick = [0.0]
    t = datetime(2026, 11, 11, tzinfo=timezone.utc)
    m = SourceTelemetry(clock=lambda: tick[0], utcnow=lambda: t)
    assert m.observe_pcm("game", "radio", 0)
    assert m.snapshot("game", "radio")["signal"] == "no_audio"
    m.observe_pcm("game", "youtube", 1)
    m.observe_text("game", "youtube", "replay",captured_at=t+timedelta(seconds=30),
                   processed_at=t)
    youtube = m.snapshot("game", "youtube")
    assert youtube["signal"] == "online"
    assert youtube["content"] == "other"
    assert youtube["processing_delay_seconds"] is None
    assert m.snapshot("game", "radio")["content"] == "unknown"
    assert m.snapshot("other", "youtube")["signal"] == "unobserved"
    with pytest.raises(ValueError): m.observe_pcm("game", "radio", -1)
    with pytest.raises(ValueError): m.observe_pcm("game", "radio", True)
