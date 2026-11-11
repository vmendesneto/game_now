"""GN-071: frontend guardrails and Node verification of explicit-region display."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_region_status_uses_accessible_uncertainty_and_bounded_motion():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert html.index("field_geometry.js") < html.index(
        "pitch_presentation.js") < html.index("app.js")
    assert 'id="ball-status" role="status" aria-live="polite"' in html
    assert "GameNowPresentation.presentBall(" in js
    assert "if(view.visible)" in js
    assert "previousRenderedEventId" in js
    assert "view.animate" in js
    assert "zoneCellBounds(view.zone,view.direction)" in js
    assert "region-change" in css and "@keyframes region-evidence" in css
    assert "prefers-reduced-motion:reduce" in css
    assert "translate" not in css.split("/* GN-071:")[-1]


def test_node_safe_pitch_presentation():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is provided in CI; not required for Windows end users")
    scripts = [STATIC / "pitch_presentation.js", STATIC / "app.js"]
    for script in scripts:
        syntax = subprocess.run(
            [node, "--check", str(script)],
            capture_output=True, text=True, timeout=15,
        )
        assert syntax.returncode == 0, syntax.stderr
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests" / "test_pitch_presentation.cjs")],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "# fail 0" in result.stdout
