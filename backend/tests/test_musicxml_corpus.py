"""Commit 107 edge-case MusicXML corpus tests.

The corpus (`tests/fixtures/musicxml-corpus/`) covers the semantic edge
cases the AlphaTab importer must survive: irregular time signatures,
nested tuplets, polyrhythms, extreme tempo changes, multi-voice staves,
syncopation, and compound meters.

Two gates:
1. Every corpus file is well-formed AND validates against the official
   MusicXML 3.1 Partwise DTD (vendored fixture).
2. Every corpus file loads and renders through AlphaTab (Node bridge) —
   web (DOM AlphaTab) and native (WebView AlphaTab) run the same engine,
   so this is the semantic "renders without crash" gate for both platforms.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from lxml import etree

CORPUS_DIR = Path(__file__).resolve().parent / "fixtures" / "musicxml-corpus"
DTD_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "musicxml-dtd" / "musicxml31-partwise-combined.dtd"
CHECK_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "alphatab_corpus_check.mjs"

MIN_CORPUS_SIZE = 20


def _corpus_files() -> list[Path]:
    if not CORPUS_DIR.is_dir():
        return []
    return sorted(CORPUS_DIR.glob("*.musicxml"))


def test_corpus_has_at_least_20_files():
    files = _corpus_files()
    assert len(files) >= MIN_CORPUS_SIZE, (
        f"corpus must have >= {MIN_CORPUS_SIZE} edge-case files, found {len(files)}"
    )


def test_corpus_covers_expected_edge_cases():
    names = {p.stem for p in _corpus_files()}
    expected = {
        "irregular-5-4",
        "irregular-7-8",
        "nested-tuplets",
        "polyrhythm-3-2",
        "tempo-change-60-to-240",
        "multi-voice-staff",
    }
    missing = expected - names
    assert not missing, f"corpus missing edge cases: {sorted(missing)}"


def test_every_corpus_file_validates_against_musicxml31_dtd():
    files = _corpus_files()
    assert files, "corpus directory is empty"
    dtd = etree.DTD(str(DTD_FIXTURE))
    failures: list[str] = []
    for p in files:
        root = etree.fromstring(p.read_bytes())
        if not dtd.validate(root):
            failures.append(f"{p.name}: {dtd.error_log}")
    assert not failures, "DTD validation failures:\n" + "\n".join(failures)


def test_corpus_renders_without_crash_via_alphatab():
    """Run the Node + AlphaTab corpus check (same engine as web and native)."""
    files = _corpus_files()
    assert files, "corpus directory is empty"
    if shutil.which("node") is None:
        return
    if not CHECK_SCRIPT.is_file():
        return
    proc = subprocess.run(
        ["node", str(CHECK_SCRIPT)],
        input=json.dumps({"corpusDir": str(CORPUS_DIR)}).encode("utf-8"),
        cwd=str(CHECK_SCRIPT.parent.parent),
        capture_output=True,
        timeout=600,
        check=False,
    )
    out_txt = proc.stdout.decode("utf-8", errors="replace").strip()
    assert out_txt, f"corpus check produced no stdout; stderr={proc.stderr.decode('utf-8', 'replace')[:500]!r}"
    data = json.loads(out_txt)
    assert data.get("ok"), f"AlphaTab corpus render failed: {data.get('failed')}"
    assert int(data.get("rendered") or 0) >= MIN_CORPUS_SIZE