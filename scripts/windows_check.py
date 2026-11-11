"""GN-091: read-only local installation checklist, usable without a Windows login.

Never starts capture, downloads models, modifies files or scans external hosts.
The optional --health probe contacts 127.0.0.1:8000 only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from urllib.error import URLError
from urllib.request import urlopen


HEALTH_URL = "http://127.0.0.1:8000/health"
REQUIRED_MODULES = ("fastapi", "uvicorn", "pydantic")


def _python_supported() -> bool:
    return sys.version_info[:2] in ((3, 11), (3, 12))


def _module_ready(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _find_executable(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    # Running .venv\Scripts\python.exe directly does not activate the venv PATH.
    sibling = Path(sys.executable).parent / (name + (".exe" if platform.system() == "Windows" else ""))
    return str(sibling) if sibling.is_file() else None


def _executable_version(path: str | None) -> str | None:
    if not path:
        return None
    try:
        run = subprocess.run([path, "-version" if "ffmpeg" in Path(path).name.lower() else "--version"],
                             check=False, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if run.returncode != 0:
        return None
    return (run.stdout or run.stderr).splitlines()[0][:180] if (run.stdout or run.stderr) else None


def _local_health() -> dict[str, object]:
    try:
        with urlopen(HEALTH_URL, timeout=3) as response:
            if response.status != 200:
                return {"status": "unavailable", "http_status": response.status}
            data = json.loads(response.read(128_000))
        if (not isinstance(data, dict) or data.get("status") != "ok"
                or data.get("mode") != "synthetic_demo" or "storage" not in data):
            return {"status": "unexpected_response"}
        return {"status": "ok", "mode": data["mode"]}
    except (OSError, ValueError, URLError):
        return {"status": "unavailable"}


def diagnostics(*, check_health: bool = False) -> dict[str, object]:
    modules = {module: _module_ready(module) for module in REQUIRED_MODULES}
    ffmpeg_path = _find_executable("ffmpeg")
    ytdlp_path = _find_executable("yt-dlp")
    python_ok = _python_supported()
    demo_ready = python_ok and all(modules.values())
    report: dict[str, object] = {
        "os": platform.system(),
        "python": platform.python_version(),
        "python_supported": python_ok,
        "modules": modules,
        "ffmpeg": {"available": bool(ffmpeg_path), "version": _executable_version(ffmpeg_path)},
        "yt_dlp": {"available": bool(ytdlp_path), "version": _executable_version(ytdlp_path)},
        "faster_whisper_optional_installed": _module_ready("faster_whisper"),
        "demo_ready": demo_ready,
        "radio_tools_ready": demo_ready and bool(ffmpeg_path),
        "youtube_tools_ready": demo_ready and bool(ffmpeg_path) and bool(ytdlp_path),
        "health": _local_health() if check_health else {"status": "not_checked"},
        "no_external_network_test": True,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GN-091: verificar instalação local do Game Now")
    parser.add_argument("--health", action="store_true", help="consultar apenas http://127.0.0.1:8000/health")
    parser.add_argument("--json", action="store_true", help="imprimir relatório em formato JSON")
    args = parser.parse_args(argv)
    result = diagnostics(check_health=args.health)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Game Now — verificação local (GN-091)")
        print(f"Sistema: {result['os']} | Python: {result['python']} | versão suportada: {result['python_supported']}")
        print(f"Bibliotecas da demo: {result['modules']}")
        print(f"Demo pronta: {result['demo_ready']}")
        print(f"FFmpeg: {result['ffmpeg']} | yt-dlp: {result['yt_dlp']}")
        print(f"Captura rádio pronta: {result['radio_tools_ready']} | YouTube: {result['youtube_tools_ready']}")
        print(f"Servidor local: {result['health']}")
        print("Não testa modelos, direitos de uso, transmissão real, nem validação física do Windows.")
    return 0 if result["demo_ready"] and (not args.health or result["health"]["status"] == "ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
