"""GN-012: bootstrap the local Windows demo without a shell or media capture.

This module is invoked by iniciar_windows.bat using a supported system Python,
or the already-created virtualenv interpreter. Windows execution still requires
physical validation; cross-platform unit tests verify process orchestration.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_PYTHON = ((3, 11), (3, 12))


class StartupError(RuntimeError):
    """User-actionable bootstrap failure."""


def venv_python(root: Path) -> Path:
    return root / ".venv" / "Scripts" / "python.exe"


def _require_version(executable: Path, root: Path) -> None:
    """Reject stale virtualenvs and unsupported versions before any pip write."""
    command = [str(executable), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"]
    try:
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StartupError("Nao foi possivel executar Python. Verifique a instalacao ou a .venv.") from exc
    if result.returncode != 0 or result.stdout.strip() not in ("3.11", "3.12"):
        raise StartupError("Game Now requer Python 3.11 ou 3.12. Corrija a instalacao/.venv antes de iniciar.")


def _run(command: list[str], root: Path, *, step: str) -> int:
    try:
        result = subprocess.run(command, cwd=root, check=False)
    except OSError as exc:
        raise StartupError(f"Falha ao executar {step}. Verifique permissoes e instalacao.") from exc
    return result.returncode


def prepare_environment(root: Path = ROOT, *, bootstrap_python: Path | None = None) -> Path:
    """Create the venv if needed, but never delete or overwrite an existing one."""
    bootstrap_python = bootstrap_python or Path(sys.executable)
    _require_version(bootstrap_python, root)
    virtualenv = root / ".venv"
    python = venv_python(root)
    if not python.is_file():
        if virtualenv.exists():
            raise StartupError(".venv existe mas nao tem Scripts\\python.exe. Renomeie-a apos verificar seus dados.")
        print("Criando ambiente virtual Python do Game Now...", flush=True)
        if _run([str(bootstrap_python), "-m", "venv", str(virtualenv)], root, step="venv") != 0:
            raise StartupError("Falha ao criar .venv. Confira permissoes e o modulo venv do Python.")
        if not python.is_file():
            raise StartupError("A criacao de .venv nao produziu Scripts\\python.exe.")
    _require_version(python, root)
    return python


def run_demo(root: Path = ROOT, *, bootstrap_python: Path | None = None) -> int:
    python = prepare_environment(root, bootstrap_python=bootstrap_python)
    requirements = root / "requirements.txt"
    if not requirements.is_file():
        raise StartupError("requirements.txt nao encontrado na pasta do Game Now.")
    print("Verificando dependencias da demo (sem modelos ASR)...", flush=True)
    if _run([str(python), "-m", "pip", "install", "-r", str(requirements)], root, step="pip") != 0:
        raise StartupError("Instalacao das dependencias falhou. Confira internet/PyPI e tente novamente.")
    print("Game Now (demo local): http://127.0.0.1:8000", flush=True)
    print("Use Ctrl+C para encerrar. Nao expoe a porta para a rede.", flush=True)
    return _run(
        [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        root, step="servidor",
    )


def main() -> int:
    try:
        if sys.version_info[:2] not in SUPPORTED_PYTHON:
            raise StartupError("Python inicial deve ser 3.11 ou 3.12.")
        return run_demo()
    except StartupError as exc:
        print(f"Game Now: {exc}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
