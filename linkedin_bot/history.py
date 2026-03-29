"""Draft history module for the LinkedIn networking bot.

History is stored as append-only JSONL at drafts/history.jsonl relative to
the working directory.  Each line is a JSON object with the schema::

    {
        "url": "https://www.linkedin.com/in/...",
        "timestamp": "2026-03-28T15:30:00Z",
        "persona": "founder",
        "target_name": "Sarah Chen",
        "target_role": "Head of ML @ Stripe",
        "angles": ["angle 1 text", "angle 2 text", "angle 3 text"],
        "chosen_index": None   # or 0, 1, 2 after user selects
    }
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HISTORY_FILE = Path("drafts/history.jsonl")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_dir(path: Path) -> None:
    """Create parent directory for *path* if it does not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_all(path: Path) -> list[dict]:
    """Read every valid JSONL entry from *path*.

    Missing files return an empty list.  Corrupt lines are skipped with a
    warning written to stderr so callers never receive a crash.
    """
    if not path.exists():
        return []

    entries: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entries.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                print(
                    f"[history] WARNING: skipping corrupt line {lineno} in "
                    f"{path}: {exc}",
                    file=sys.stderr,
                )
    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def append_entry(entry: dict) -> None:
    """Append *entry* to the history file.

    Creates the ``drafts/`` directory and the file itself if they do not yet
    exist.
    """
    _ensure_dir(HISTORY_FILE)
    with HISTORY_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_recent_for_url(url: str, limit: int = 3) -> list[dict]:
    """Return the last *limit* entries for *url*, most recent first.

    Returns an empty list when the history file does not exist or when no
    entries match *url*.
    """
    entries = _read_all(HISTORY_FILE)
    matching = [e for e in entries if e.get("url") == url]
    # Most recent first; rely on timestamp string sort (ISO 8601 sorts lexicographically)
    matching.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return matching[:limit]


def update_chosen_index(url: str, timestamp: str, chosen_index: int) -> None:
    """Update ``chosen_index`` for the entry identified by (*url*, *timestamp*).

    Rewrites the entire file in place.  If no matching entry is found the
    function returns silently without modifying anything.
    """
    entries = _read_all(HISTORY_FILE)

    updated = False
    for entry in entries:
        if entry.get("url") == url and entry.get("timestamp") == timestamp:
            entry["chosen_index"] = chosen_index
            updated = True
            break

    if not updated:
        return

    _ensure_dir(HISTORY_FILE)
    with HISTORY_FILE.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def list_recent(limit: int = 20) -> list[dict]:
    """Return the last *limit* entries across all URLs, most recent first."""
    entries = _read_all(HISTORY_FILE)
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return entries[:limit]


def format_entry_summary(entry: dict) -> str:
    """Return a single-line human-readable summary of *entry*.

    Format: ``YYYY-MM-DD | <persona> | <target_name> @ <company> | <url>``

    The ``target_role`` is split on ``@`` to extract the company; if no ``@``
    is present the full role string is used instead.
    """
    # Date portion only from the ISO timestamp
    raw_ts: str = entry.get("timestamp", "")
    date_part = raw_ts[:10] if raw_ts else "unknown-date"

    persona: str = entry.get("persona", "")
    target_name: str = entry.get("target_name", "")
    target_role: str = entry.get("target_role", "")
    url: str = entry.get("url", "")

    # Extract company from "Title @ Company"
    if "@" in target_role:
        company = target_role.split("@", 1)[1].strip()
    else:
        company = target_role

    return f"{date_part} | {persona} | {target_name} @ {company} | {url}"


def make_entry(
    url: str,
    persona: str,
    target_name: str,
    target_role: str,
    angles: list[str],
    chosen_index: int | None = None,
    timestamp: str | None = None,
) -> dict:
    """Convenience factory that builds a history entry dict.

    If *timestamp* is omitted the current UTC time is used.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "url": url,
        "timestamp": timestamp,
        "persona": persona,
        "target_name": target_name,
        "target_role": target_role,
        "angles": angles,
        "chosen_index": chosen_index,
    }
