"""Tests for the pip-audit baseline gate (Commit 7)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_SCRIPT = _BACKEND_DIR / "scripts" / "check_pip_audit.py"
_BASELINE = _BACKEND_DIR / "security" / "pip-audit-baseline.json"


def _run(tmp_path: Path, report: dict) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "pip-audit.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_accepted_ids_pass(tmp_path: Path) -> None:
    accepted = json.loads(_BASELINE.read_text(encoding="utf-8"))["accepted_ids"][0]
    report = {
        "dependencies": [
            {"name": "torch", "version": "2.5.1", "vulns": [{"id": accepted}]}
        ]
    }
    result = _run(tmp_path, report)
    assert result.returncode == 0, result.stderr


def test_new_vulnerability_fails(tmp_path: Path) -> None:
    report = {
        "dependencies": [
            {"name": "pkg", "version": "1.0.0", "vulns": [{"id": "GHSA-NEW-TEST"}]}
        ]
    }
    result = _run(tmp_path, report)
    assert result.returncode == 1
    assert "GHSA-NEW-TEST" in result.stderr
    assert "New Python vulnerabilities" in result.stderr


def test_clean_report_passes(tmp_path: Path) -> None:
    result = _run(tmp_path, {"dependencies": []})
    assert result.returncode == 0, result.stderr
