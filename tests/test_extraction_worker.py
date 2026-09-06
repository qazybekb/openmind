"""Exercise real parser-process termination, not just pre/post clock checks."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from openmind import materials
from tests.test_hardening import pptx


@pytest.mark.parametrize("kind", ["pdf", "pptx", "docx"])
def test_a_blocking_parser_is_killed_and_reaped(kind, monkeypatch):
    processes = []
    original = subprocess.Popen

    def start(*args, **kwargs):
        process = original(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(materials, "MAX_SECONDS", 0.2)
    monkeypatch.setattr(materials, "_worker_command", lambda _: [sys.executable, "-c", "import time; time.sleep(60)"])
    monkeypatch.setattr(subprocess, "Popen", start)
    started = time.monotonic()
    result = getattr(materials, f"extract_{kind}")(b"input")
    elapsed = time.monotonic() - started
    assert result.status == "failed" and result.truncated
    assert "time limit" in result.note
    assert elapsed < 5
    assert processes and all(process.poll() is not None for process in processes)


def test_worker_does_not_inherit_canvas_credentials(monkeypatch):
    monkeypatch.setenv("OPENMIND_CANVAS_TOKEN", "synthetic-secret")
    script = (
        "import json, os; "
        "print(json.dumps({'pages': [str('OPENMIND_CANVAS_TOKEN' in os.environ)], 'char_count': 5}))"
    )
    monkeypatch.setattr(materials, "_worker_command", lambda _: [sys.executable, "-c", script])
    assert materials.extract_pdf(b"input").pages == ["False"]


def test_worker_applies_the_parent_character_cap(monkeypatch):
    monkeypatch.setattr(materials, "MAX_CHARS", 100)
    result = materials.extract_pptx(pptx(["text " * 100]))
    assert result.status == "indexed" and result.truncated
    assert result.char_count <= 100


def test_worker_failure_is_reported_without_leaking_its_output(monkeypatch):
    monkeypatch.setattr(materials, "_worker_command", lambda _: [
        sys.executable, "-c", "import sys; print('private document', file=sys.stderr); sys.exit(1)"
    ])
    result = materials.extract_pdf(b"input")
    assert result.status == "failed" and "private document" not in str(result)


@pytest.mark.skipif(os.name == "nt", reason="POSIX resource limits")
def test_worker_disables_core_dumps():
    script = (
        "import resource; from openmind.extract_worker import restrict_resources; "
        "restrict_resources(); print(resource.getrlimit(resource.RLIMIT_CORE)[0])"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "0"
