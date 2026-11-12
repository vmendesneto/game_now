"""Verify the schematic marker policy in Node, independent of ASR/network."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_marker_is_loaded_before_render_and_its_visibility_policy_runs_in_node():
    root = Path(__file__).resolve().parents[1]
    html = (root / "app/static/index.html").read_text(encoding="utf-8")
    assert html.index("field_geometry.js") < html.index("ball_marker.js") < html.index("app.js")
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is available in CI")
    result = subprocess.run([node, "--test", str(root / "tests/test_ball_marker.cjs")],
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# fail 0" in result.stdout
