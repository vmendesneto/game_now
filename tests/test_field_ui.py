"""GN-070: frontend layout invariants and portable Node geometry tests."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_mobile_svg_uses_fixed_viewbox_and_loaded_geometry_before_render():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
    assert 'viewBox="0 0 1000 620"' in html
    assert 'preserveAspectRatio="xMidYMid meet"' in html
    assert html.index('src="/static/field_geometry.js') < html.index(
        'src="/static/app.js')  # Cache version query must not change load order.
    assert "aspect-ratio:1000/620" in css
    assert "max-width:100%" in css
    assert "@media(max-width:600px)" in css
    assert "zoneCellBounds(view.zone,view.direction)" in script
    assert 'data-grid-cell' in script
    assert "field.setAttribute(\"aria-label\"" in script


def test_field_geometry_and_frontend_javascript_syntax():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed; GitHub Actions runner executes this test")
    for file in (STATIC / "field_geometry.js", STATIC / "app.js"):
        result = subprocess.run(
            [node, "--check", str(file)], capture_output=True,
            text=True, timeout=15, check=False,
        )
        assert result.returncode == 0, result.stderr


def test_pure_field_geometry_in_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js not installed; GitHub Actions runner executes this test")
    result = subprocess.run(
        [node, "--test", str(ROOT / "tests" / "test_field_geometry.cjs")],
        cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "# fail 0" in result.stdout
