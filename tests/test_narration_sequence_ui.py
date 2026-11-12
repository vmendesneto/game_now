from pathlib import Path
import shutil
import subprocess
import pytest

def test_text_sequence_policy_and_load_order():
    root=Path(__file__).resolve().parents[1]
    html=(root/"app/static/index.html").read_text(encoding="utf-8")
    assert html.index("narration_sequence.js")<html.index("app.js")
    node=shutil.which("node")
    if not node:pytest.skip("Node available in CI")
    result=subprocess.run([node,"--test",str(root/"tests/test_narration_sequence.cjs")],capture_output=True,text=True,encoding="utf-8",timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
