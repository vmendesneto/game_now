"""GN-036: opt-in energy filter, counterexamples and synthetic benchmark."""
import math
import struct
import pytest

from app.asr_windows import RollingASRProcessor, WindowSettings
from app.asr import ASRResult
from app.silence_gate import PCMSilenceGate, SilenceGateSettings
from scripts.benchmark_gn036_silence import benchmark, fixtures


def test_energy_gate_is_not_ad_detector_and_is_conservative():
    gate=PCMSilenceGate()
    examples=dict(fixtures())
    assert gate.assess(examples["silence_pre"]).skip_asr
    assert not gate.assess(examples["narration_like_tone"]).skip_asr
    assert not gate.assess(examples["commercial_like_tone"]).skip_asr
    weak=struct.pack("<h",20)*16000
    assert gate.assess(weak).skip_asr
    assertion=gate.assess(examples["commercial_like_tone"])
    assert assertion.reason=="pcm_activity"
    assert assertion.active_ms>=90
    with pytest.raises(ValueError,match="aligned"):
        gate.assess(bytes([0]))
    with pytest.raises(ValueError,match="nonempty"):
        gate.assess(bytes([0]))
    with pytest.raises(ValueError,match="threshold"):
        SilenceGateSettings(rms_threshold=math.inf)


def test_opt_in_skips_silence_without_compressing_window_time():
    result=benchmark()
    assert result["baseline_inference_calls"]==4
    assert result["gated_inference_calls"]==2
    assert result["calls_avoided_percent"]==50.0
    assert result["gated_sequences"]==[1,2]
    assert result["time_alignment_preserved"]
    assert not result["advertisement_detected"]
    assert not result["real_asr_model_used"]
    assert not result["actual_windows_tested"]


def test_default_processor_remains_unchanged():
    class Dummy:
        def __init__(self): self.calls=0
        def transcribe_pcm(self,block):
            self.calls+=1
            return ASRResult(model="fake",language="pt",
                             seconds=len(block)/32000,text="texto",segments=())
    dummy=Dummy()
    engine=RollingASRProcessor(dummy,WindowSettings(
        window_ms=1000,overlap_ms=1,min_tail_ms=500))
    for _label,pcm in fixtures():
        engine.push("source",pcm)
    assert dummy.calls==4


def test_gate_does_not_drop_short_loud_exclamation():
    gate=PCMSilenceGate(SilenceGateSettings(min_active_ms=90))
    loud=struct.pack("<h",8000)*int(16000*0.06)
    assert not gate.assess(loud).skip_asr
