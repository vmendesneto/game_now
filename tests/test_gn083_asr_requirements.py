"""Guard compatibility of the optional CPU-ASR dependency pair.

This test checks the pinned installation contract; the real CPU inference smoke
check is run on the user's Windows via scripts.gn083_asr_check.
"""
from pathlib import Path


def test_faster_whisper_and_pyav_compatible_pins():
    requirements = (Path(__file__).resolve().parents[1] / "requirements-asr.txt")
    effective = [line.strip() for line in requirements.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
    assert "faster-whisper==1.2.1" in effective
    assert "av==17.1.0" in effective
    assert len([line for line in effective if line.startswith("av")]) == 1
