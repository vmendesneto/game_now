"""Platform adapters for synthetic subprocess fixtures, never production commands."""
import asyncio
import os
from pathlib import Path
import sys

import pytest


@pytest.fixture
def python_script_launchers(monkeypatch, tmp_path):
    """Windows has no POSIX shebang loader; run our temporary Python stubs explicitly.

    Still creates real subprocesses, including their pipes, timeout and cleanup.
    Limited to scripts inside this test's directory; native executables are intact.
    """
    if os.name != "nt":
        return
    original = asyncio.create_subprocess_exec

    async def launch(program, *args, **kwargs):
        path = Path(program).resolve()
        if path.is_relative_to(tmp_path.resolve()) and path.is_file():
            with path.open("rb") as stream:
                python_stub = stream.readline().strip() == b"#!/usr/bin/env python3"
            if python_stub:
                return await original(sys.executable, str(path), *args, **kwargs)
        return await original(program, *args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
