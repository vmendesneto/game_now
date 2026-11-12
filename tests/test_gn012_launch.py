"""GN-012 bootstrap tests. These do NOT validate physical Windows."""
from pathlib import Path
import subprocess

import pytest
from scripts import gn012_launch as launcher


def _root(tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi==0.128.2\n")
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_text("fake")
    return tmp_path


def _stub(monkeypatch, calls, *, fail_step=None, python_version="3.12", server_exit=0):
    def fake_run(command, **options):
        calls.append((command, options))
        if command[1] == "-c":
            return subprocess.CompletedProcess(command, 0, stdout=python_version + "\n", stderr="")
        if fail_step is not None and fail_step in command:
            return subprocess.CompletedProcess(command, 4)
        return subprocess.CompletedProcess(command, server_exit if "uvicorn" in command else 0)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)


def test_existing_venv_installs_before_local_server(monkeypatch, tmp_path):
    root = _root(tmp_path)
    calls = []
    _stub(monkeypatch, calls)
    assert launcher.run_demo(root, bootstrap_python=Path("system-python")) == 0
    command_list = [c for c, _ in calls]
    assert all(options.get("cwd") == root for _, options in calls)
    assert len([c for c in command_list if "venv" in c]) == 0
    assert command_list[-2][1:5] == ["-m", "pip", "install", "-r"]
    assert command_list[-1] == [str(launcher.venv_python(root)), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]
    assert all(options.get("shell") is not True for _, options in calls)


def test_new_environment_uses_selected_interpreter(monkeypatch, tmp_path):
    (tmp_path / "requirements.txt").write_text("fastapi==0.128.2\n")
    calls = []
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "venv" in cmd:
            p = launcher.venv_python(tmp_path)
            p.parent.mkdir(parents=True)
            p.write_text("fake")
        return subprocess.CompletedProcess(cmd, 0, stdout="3.11\n", stderr="")
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    assert launcher.run_demo(tmp_path, bootstrap_python=Path("system-python")) == 0
    assert calls[1] == ["system-python", "-m", "venv", str(tmp_path / ".venv")]


def test_unsupported_version_never_runs_pip_or_server(monkeypatch, tmp_path):
    root = _root(tmp_path)
    calls = []
    _stub(monkeypatch, calls, python_version="3.13")
    with pytest.raises(launcher.StartupError, match="3.11 ou 3.12"):
        launcher.run_demo(root, bootstrap_python=Path("system-python"))
    assert all("pip" not in c and "uvicorn" not in c for c, _ in calls)


def test_broken_existing_venv_is_not_replaced(monkeypatch, tmp_path):
    root = tmp_path
    (root / ".venv").mkdir()
    calls = []
    _stub(monkeypatch, calls)
    with pytest.raises(launcher.StartupError, match="Renomeie-a"):
        launcher.prepare_environment(root, bootstrap_python=Path("system-python"))
    assert all("venv" not in c for c, _ in calls)


def test_failed_pip_prevents_server(monkeypatch, tmp_path):
    root = _root(tmp_path)
    calls = []
    _stub(monkeypatch, calls, fail_step="pip")
    with pytest.raises(launcher.StartupError, match="dependencias falhou"):
        launcher.run_demo(root, bootstrap_python=Path("system-python"))
    assert not any("uvicorn" in c for c, _ in calls)


def test_server_exit_is_propagated(monkeypatch, tmp_path):
    root = _root(tmp_path)
    calls = []
    _stub(monkeypatch, calls, server_exit=7)
    assert launcher.run_demo(root, bootstrap_python=Path("system-python")) == 7


def test_venv_creation_failure_does_not_install(monkeypatch, tmp_path):
    calls = []
    _stub(monkeypatch, calls, fail_step="venv")
    with pytest.raises(launcher.StartupError, match="criar .venv"):
        launcher.prepare_environment(tmp_path, bootstrap_python=Path("system-python"))
    assert not any("pip" in c for c, _ in calls)


def test_windows_bat_uses_repo_path_and_supported_launchers():
    bat = (Path(__file__).resolve().parents[1] / "iniciar_windows.bat").read_text()
    assert 'cd /d "%~dp0"' in bat
    assert 'py -3.12 -m scripts.gn012_launch' in bat
    assert 'py -3.11 -m scripts.gn012_launch' in bat
    assert 'python -m scripts.gn012_launch' in bat
    assert '".venv\\Scripts\\python.exe" -m scripts.gn012_launch' in bat
    assert "--host 0.0.0.0" not in bat


def test_clean_demo_installs_websocket_transport():
    """TestClient alone doesn't exercise Uvicorn's optional wire transport."""
    root = Path(__file__).resolve().parents[1]
    requirements = (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert "websockets==17.4" in requirements
