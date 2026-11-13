"""Fail when pip-audit reports a vulnerability outside the accepted baseline.

Usage:
    python scripts/check_pip_audit.py pip-audit.json

The baseline is ``backend/security/pip-audit-baseline.json``. A finding whose
ID is not listed there fails the check. Accepted IDs carry a review date; an
expired baseline prints a warning so it gets re-reviewed.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_BASELINE = _BACKEND_DIR / "security" / "pip-audit-baseline.json"


def _load_json(path: Path, label: str) -> dict:
    if not path.is_file():
        raise SystemExit(f"{label} not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{label} is not valid JSON: {path}: {exc}") from exc


def _accepted_ids(baseline: dict) -> set[str]:
    ids = baseline.get("accepted_ids")
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise SystemExit(
            f"Baseline must contain a string list 'accepted_ids': {_BASELINE}"
        )
    return set(ids)


def _warn_if_expired(baseline: dict) -> None:
    expires = baseline.get("expires")
    if not expires:
        return
    try:
        expired = date.fromisoformat(expires) < date.today()
    except ValueError:
        print(f"WARNING: invalid baseline expiry date: {expires!r}", file=sys.stderr)
        return
    if expired:
        print(
            f"WARNING: pip-audit baseline expired on {expires} "
            f"(owner: {baseline.get('owner', 'unknown')}); re-review it.",
            file=sys.stderr,
        )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_pip_audit.py <pip-audit.json>", file=sys.stderr)
        return 2

    report = _load_json(Path(argv[1]), "pip-audit report")
    baseline = _load_json(_BASELINE, "pip-audit baseline")
    accepted = _accepted_ids(baseline)
    _warn_if_expired(baseline)

    findings: set[tuple[str, str, str]] = set()
    for dep in report.get("dependencies", []):
        name = str(dep.get("name", "?"))
        version = str(dep.get("version", "?"))
        for vuln in dep.get("vulns", []):
            finding_id = str(vuln.get("id", "?"))
            if finding_id not in accepted:
                findings.add((name, version, finding_id))

    if findings:
        print(
            "New Python vulnerabilities not in the accepted baseline:",
            file=sys.stderr,
        )
        for name, version, finding_id in sorted(findings):
            print(f"  {name}=={version}  {finding_id}", file=sys.stderr)
        print(
            "\nReview the finding, then update "
            f"{_BASELINE} if it is accepted.",
            file=sys.stderr,
        )
        return 1

    print(f"pip-audit: no new vulnerabilities ({len(accepted)} accepted IDs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
