"""Synthesize deterministic-ish Portuguese WAV fixtures without apt or espeak CLI.

This helper is used only by opt-in real-ASR smoke tests. It uses the
bundled espeak-ng shared library + language data in espeakng-loader; it
does not download audio or send speech to a hosted service.
"""
from __future__ import annotations

import ctypes
from pathlib import Path
import wave


def synthesize_wav(
    text: str,
    output_path: str | Path,
    *,
    language: str = "pt-br",
    words_per_minute: int = 130,
) -> Path:
    """Write a 16-bit mono WAV from eSpeak NG's synchronous PCM callback."""
    if not text.strip() or not 80 <= words_per_minute <= 450:
        raise ValueError("Speech text and speaking rate must be valid")
    if len(text) > 2048:
        raise ValueError("Speech fixture text is too long")
    if language not in ("pt-br", "pt"):
        raise ValueError("Only the Portuguese synthetic test voice is supported")

    try:
        import espeakng_loader
    except ImportError as exc:
        raise RuntimeError(
            "Install espeakng-loader==0.2.4 for real CPU ASR smoke tests"
        ) from exc

    lib = ctypes.CDLL(espeakng_loader.get_library_path())
    # espeak_Initialize expects the parent directory of espeak-ng-data.
    data_parent = str(Path(espeakng_loader.get_data_path()).parent).encode()
    lib.espeak_Initialize.argtypes = [
        ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
    ]
    lib.espeak_Initialize.restype = ctypes.c_int
    # Synchronous output = 2. The C callback receives mono s16 samples.
    sample_rate = lib.espeak_Initialize(2, 0, data_parent, 0)
    if sample_rate <= 0:
        raise RuntimeError("Failed to initialize offline eSpeak NG")
    blocks: list[bytes] = []
    callback_type = ctypes.CFUNCTYPE(
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.c_void_p,
    )

    @callback_type
    def callback(samples, count, _events):
        if samples and count > 0:
            blocks.append(ctypes.string_at(samples, count * 2))
        return 0

    try:
        lib.espeak_SetSynthCallback.argtypes = [callback_type]
        lib.espeak_SetSynthCallback(callback)
        lib.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
        lib.espeak_SetVoiceByName.restype = ctypes.c_int
        # The eSpeak NG bundle exposes pt or pt-br depending on its voice data.
        if all(
            lib.espeak_SetVoiceByName(name.encode()) != 0
            for name in (language, "pt", "brazil")
        ):
            raise RuntimeError("No compatible Portuguese eSpeak NG voice")

        lib.espeak_SetParameter.argtypes = [
            ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ]
        lib.espeak_SetParameter.restype = ctypes.c_int
        if lib.espeak_SetParameter(1, words_per_minute, 0) != 0:
            raise RuntimeError("Could not set eSpeak NG speaking rate")

        lib.espeak_Synth.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int,
            ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint),
            ctypes.c_void_p,
        ]
        lib.espeak_Synth.restype = ctypes.c_int
        payload = ctypes.create_string_buffer(text.encode("utf-8") + b"\x00")
        if lib.espeak_Synth(
            payload, len(payload), 0, 0, 0, 1, None, None,
        ) != 0:
            raise RuntimeError("eSpeak NG failed to synthesize speech")
        lib.espeak_Synchronize.argtypes = []
        lib.espeak_Synchronize.restype = ctypes.c_int
        if lib.espeak_Synchronize() != 0:
            raise RuntimeError("eSpeak NG did not finish synthesis")
    finally:
        lib.espeak_Terminate.argtypes = []
        lib.espeak_Terminate()

    if not blocks or sum(map(len, blocks)) < sample_rate:
        raise RuntimeError("eSpeak NG produced insufficient PCM audio")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(b"".join(blocks))
    return output
