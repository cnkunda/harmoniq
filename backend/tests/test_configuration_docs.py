"""Guard: every backend env read is documented in docs/CONFIGURATION.md."""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_DIR = _REPO_ROOT / "backend" / "app"
_CONFIG_DOC = _REPO_ROOT / "docs" / "CONFIGURATION.md"

# os.getenv("NAME") / os.environ.get("NAME"); \s* also matches multi-line args.
_ENV_READ_RE = re.compile(
    r"""os\s*\.\s*(?:getenv|environ\s*\.\s*get)\(\s*["']([A-Z][A-Z0-9_]*)["']"""
)

# Read through variables, so the literal scan above cannot see them.
_DYNAMIC_ENV_READS = {
    "HARMONIQ_CONFIDENCE_GATE",
    "HARMONIQ_ENABLE_PRERENDER",
    "HARMONIQ_SKIP_PRERENDER",
    "HARMONIQ_ACE_STEP_BACKING_URL",
    "HARMONIQ_MODAL_TOKEN",
    "HARMONIQ_LYRIA_BACKING_URL",
    "GEMINI_API_KEY",
}


def _literal_env_reads() -> set[str]:
    names: set[str] = set()
    for path in _APP_DIR.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        names.update(_ENV_READ_RE.findall(text))
    return names


def _missing_from_doc(names: set[str], doc: str) -> list[str]:
    return sorted(
        name
        for name in names
        if not re.search(rf"\b{re.escape(name)}\b", doc)
    )


def test_configuration_doc_exists() -> None:
    assert _CONFIG_DOC.is_file(), f"Missing environment reference: {_CONFIG_DOC}"


def test_every_literal_env_read_is_documented() -> None:
    doc = _CONFIG_DOC.read_text(encoding="utf-8")
    missing = _missing_from_doc(_literal_env_reads(), doc)
    assert not missing, (
        "Undocumented backend env reads (add them to docs/CONFIGURATION.md): "
        + ", ".join(missing)
    )


def test_every_dynamic_env_read_is_documented() -> None:
    doc = _CONFIG_DOC.read_text(encoding="utf-8")
    missing = _missing_from_doc(_DYNAMIC_ENV_READS, doc)
    assert not missing, (
        "Undocumented backend env reads (add them to docs/CONFIGURATION.md): "
        + ", ".join(missing)
    )
