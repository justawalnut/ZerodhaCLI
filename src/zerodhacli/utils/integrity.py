"""Runtime integrity checks for ZerodhaCLI sessions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from ..core.config import AppConfig, CONFIG_DIR, CONFIG_FILE

INTEGRITY_FILE = CONFIG_DIR / "integrity.json"


@dataclass(slots=True)
class IntegrityReport:
    """Represents the outcome of a session integrity check."""

    ok: bool
    digest: str
    issues: List[str]


def perform_integrity_check(config: AppConfig) -> IntegrityReport:
    """Run baseline integrity checks prior to launching a session.

    The check validates that the persisted configuration matches the
    previously recorded digest and that required live credentials exist
    when the CLI is running in live mode. The resulting digest is always
    written back to the integrity file to establish the next baseline.
    """

    digest = _config_digest()
    issues: List[str] = []
    ok = True

    previous = _load_previous()
    if previous and previous.get("config_hash") != digest:
        ok = False
        issues.append("Config file changed since last recorded run")

    if not config.dry_run:
        missing = [field for field in ("api_key", "api_secret", "access_token") if not getattr(config.creds, field)]
        if missing:
            ok = False
            issues.append(f"Missing live credential(s): {', '.join(missing)}")

    write_ok, location, error = _write_report(digest)
    if not write_ok:
        ok = False
        issues.append(f"Failed to persist integrity baseline: {error}")
    elif location != INTEGRITY_FILE:
        issues.append(f"Integrity baseline stored at {location}")
    return IntegrityReport(ok=ok, digest=digest, issues=issues)


def _config_digest() -> str:
    if not CONFIG_FILE.exists():
        return ""
    data = CONFIG_FILE.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _load_previous() -> dict:
    if not INTEGRITY_FILE.exists():
        return {}
    try:
        raw = INTEGRITY_FILE.read_text(encoding="utf-8")
        return json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_report(digest: str) -> Tuple[bool, Optional[Path], Optional[str]]:
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": digest,
    }
    data = json.dumps(payload, indent=2)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        INTEGRITY_FILE.write_text(data, encoding="utf-8")
        return True, INTEGRITY_FILE, None
    except OSError as primary_error:
        fallback = Path.cwd() / ".zerodhacli_integrity.json"
        try:
            fallback.write_text(data, encoding="utf-8")
            return True, fallback, None
        except OSError as fallback_error:
            message = f"{primary_error}; fallback error: {fallback_error}"
            return False, None, message
