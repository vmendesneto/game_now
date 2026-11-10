"""GN-034: long sessions stay bounded and keep source timestamps independent."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from app.audio_buffer import AudioFrame, BufferError, MultiSourceAudioBuffer


BASE_TIME = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
CHUNK = b"\x01\x02" * 1600  # 100ms signed 16-bit mono, 16kHz


def test_two_sources_10000_frames_each_never_exceed_memory_budget():
    buffers = MultiSourceAudioBuffer(window_seconds=10, max_bytes_per_source=320_000)
    for i in range(10_000):
        captured = BASE_TIME + timedelta(milliseconds=100 * i)
        buffers.append("radio-001", CHUNK, captured)
        buffers.append("youtube-001", CHUNK, captured)
    usage = buffers.status()
    assert set(usage) == {"radio-001", "youtube-001"}
    assert all(0 < entry["bytes"] <= 320_000 for entry in usage.values())
    assert all(0 < entry["frames"] <= 100 for entry in usage.values())
    assert all(len(buffer) <= 100 for buffer in (buffers.snapshot("radio-001"),
                                                buffers.snapshot("youtube-001")))
    assert buffers.snapshot("radio-001")[-1].captured_at == (
        BASE_TIME + timedelta(milliseconds=999_900))
    assert buffers.snapshot("radio-001")[-1].pcm == CHUNK
    assert buffers.snapshot("radio-001", BASE_TIME + timedelta(milliseconds=999_500))
    assert not buffers.snapshot("missing")
    assert sum(entry["bytes"] for entry in usage.values()) <= 640_000
    assert AudioFrame("radio-001", BASE_TIME, CHUNK).seconds == 0.1


def test_time_eviction_and_source_isolation():
    buffers = MultiSourceAudioBuffer(window_seconds=2, max_bytes_per_source=100_000)
    buffers.append("radio-1", CHUNK, BASE_TIME)
    buffers.append("radio-2", CHUNK, BASE_TIME)
    first_view = buffers.snapshot("radio-1")
    buffers.append("radio-1", CHUNK, BASE_TIME + timedelta(seconds=3))
    assert len(buffers.snapshot("radio-1")) == 1
    assert len(first_view) == 1
    assert buffers.snapshot("radio-1")[0].captured_at == BASE_TIME + timedelta(seconds=3)
    assert buffers.snapshot("radio-2")[0].captured_at == BASE_TIME
    buffers.clear("radio-1")
    assert not buffers.snapshot("radio-1")
    assert len(buffers.snapshot("radio-2")) == 1
    buffers.clear()
    assert buffers.status() == {}


def test_bad_input_out_of_order_and_source_limit_rejected_without_corruption():
    with pytest.raises(BufferError):
        MultiSourceAudioBuffer(window_seconds=0)
    with pytest.raises(BufferError):
        MultiSourceAudioBuffer(max_bytes_per_source=3)
    buffers = MultiSourceAudioBuffer(max_sources=1, max_bytes_per_source=5000)
    with pytest.raises(BufferError, match="blank"):
        buffers.append("", CHUNK, BASE_TIME)
    with pytest.raises(BufferError, match="UTC offset"):
        buffers.append("radio-1", CHUNK, datetime(2026, 11, 10))
    with pytest.raises(BufferError, match="sample-aligned"):
        buffers.append("radio-1", b"\x01", BASE_TIME)
    with pytest.raises(BufferError, match="capacity"):
        buffers.append("radio-1", CHUNK * 2, BASE_TIME)
    buffers.append("radio-1", CHUNK, BASE_TIME + timedelta(seconds=5))
    with pytest.raises(BufferError, match="backwards"):
        buffers.append("radio-1", CHUNK, BASE_TIME)
    with pytest.raises(BufferError, match="Maximum"):
        buffers.append("radio-2", CHUNK, BASE_TIME)
    assert buffers.status()["radio-1"] == {"frames": 1, "bytes": len(CHUNK)}
    with pytest.raises(BufferError, match="UTC offset"):
        buffers.snapshot("radio-1", datetime(2026, 11, 10))


def test_concurrent_independent_sources_have_consistent_snapshots():
    buffers = MultiSourceAudioBuffer(window_seconds=30, max_sources=4,
                                     max_bytes_per_source=100_000)
    def add(source):
        for i in range(500):
            buffers.append(source, CHUNK, BASE_TIME + timedelta(milliseconds=100*i))
        return source
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert set(pool.map(add, ["radio-1", "radio-2"])) == {"radio-1", "radio-2"}
    status = buffers.status()
    assert status["radio-1"] == status["radio-2"]
    assert status["radio-1"]["bytes"] <= 100_000
    assert len(buffers.snapshot("radio-1")) == status["radio-1"]["frames"]
