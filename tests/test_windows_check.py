"""GN-091: deterministic, cross-platform tests; not a physical Windows test."""
import json
from pathlib import Path
import subprocess

from scripts import windows_check as wc


def test_demo_is_independent_of_ffmpeg_and_youtube(monkeypatch):
    monkeypatch.setattr(wc, "_python_supported", lambda: True)
    monkeypatch.setattr(wc, "_module_ready", lambda name: name != "faster_whisper")
    monkeypatch.setattr(wc, "_find_executable", lambda name: None)
    result = wc.diagnostics()
    assert result["demo_ready"] is True
    assert result["radio_tools_ready"] is False
    assert result["youtube_tools_ready"] is False
    assert result["health"]["status"] == "not_checked"
    assert result["faster_whisper_optional_installed"] is False


def test_missing_required_module_makes_demo_unready(monkeypatch):
    monkeypatch.setattr(wc, "_python_supported", lambda: True)
    monkeypatch.setattr(wc, "_module_ready", lambda name: name != "uvicorn")
    monkeypatch.setattr(wc, "_find_executable", lambda name: None)
    assert wc.diagnostics()["demo_ready"] is False


def test_version_mismatch_makes_demo_unready(monkeypatch):
    monkeypatch.setattr(wc, "_python_supported", lambda: False)
    monkeypatch.setattr(wc, "_module_ready", lambda name: True)
    monkeypatch.setattr(wc, "_find_executable", lambda name: None)
    assert wc.diagnostics()["demo_ready"] is False


def test_never_probes_network_without_health_flag(monkeypatch):
    monkeypatch.setattr(wc, "urlopen", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network used")))
    wc.diagnostics(check_health=False)


def test_health_only_contacts_loopback(monkeypatch):
    calls = []
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, max_bytes):
            assert max_bytes <= 128_000
            return json.dumps({"status": "ok", "mode": "synthetic_demo", "storage": "sqlite_persistent"}).encode()
    def fake_open(url, timeout):
        calls.append((url, timeout))
        return Response()
    monkeypatch.setattr(wc, "urlopen", fake_open)
    assert wc._local_health() == {"status": "ok", "mode": "synthetic_demo"}
    assert calls == [("http://127.0.0.1:8000/health", 3)]


def test_unexpected_server_response_does_not_claim_ready(monkeypatch):
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, maximum):
            return b'{"status":"ok","mode":"other"}'
    monkeypatch.setattr(wc, "urlopen", lambda *args, **kwargs: Response())
    assert wc._local_health()["status"] == "unexpected_response"


def test_yt_dlp_executable_found_next_to_virtualenv_python(monkeypatch, tmp_path):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    exe = scripts / "yt-dlp.exe"
    exe.write_text("fake")
    monkeypatch.setattr(wc.sys, "executable", str(scripts / "python.exe"))
    monkeypatch.setattr(wc.platform, "system", lambda: "Windows")
    monkeypatch.setattr(wc.shutil, "which", lambda name: None)
    assert wc._find_executable("yt-dlp") == str(exe)


def test_executable_version_invoked_without_shell(monkeypatch):
    calls = []
    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout="ffmpeg version 7.0\n", stderr="")
    monkeypatch.setattr(wc.subprocess, "run", fake_run)
    assert wc._executable_version("ffmpeg") == "ffmpeg version 7.0"
    assert calls[0][0] == ["ffmpeg", "-version"]
    assert calls[0][1]["timeout"] == 5
    assert "shell" not in calls[0][1]


def test_json_output_is_machine_readable_and_status_truthful(monkeypatch, capsys):
    monkeypatch.setattr(wc, "diagnostics", lambda check_health=False: {
        "demo_ready": True,
        "health": {"status": "unavailable" if check_health else "not_checked"},
    })
    assert wc.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["demo_ready"] is True
    assert wc.main(["--json", "--health"]) == 1
    assert json.loads(capsys.readouterr().out)["health"]["status"] == "unavailable"


def test_readme_and_windows_script_do_not_expose_network():
    root = Path(__file__).resolve().parents[1]
    assert '"--host", "127.0.0.1"' in (root / "scripts" / "gn012_launch.py").read_text()
    assert "docs/INSTALL_WINDOWS.md" in (root / "README.md").read_text()
