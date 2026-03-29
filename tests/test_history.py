"""Tests for linkedin_bot.history — draft history module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import linkedin_bot.history as history_mod
from linkedin_bot.history import (
    append_entry,
    format_entry_summary,
    get_recent_for_url,
    list_recent,
    update_chosen_index,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_history(tmp_path, monkeypatch):
    """Point HISTORY_FILE at a temp path for every test."""
    fake_history = tmp_path / "drafts" / "history.jsonl"
    monkeypatch.setattr(history_mod, "HISTORY_FILE", fake_history)
    return fake_history


# ---------------------------------------------------------------------------
# Sample entry builder
# ---------------------------------------------------------------------------

def _entry(
    url: str = "https://www.linkedin.com/in/alice",
    timestamp: str = "2026-03-28T10:00:00Z",
    persona: str = "founder",
    target_name: str = "Alice Smith",
    target_role: str = "VP Eng @ Acme",
    angles: list[str] | None = None,
    chosen_index: int | None = None,
) -> dict:
    return {
        "url": url,
        "timestamp": timestamp,
        "persona": persona,
        "target_name": target_name,
        "target_role": target_role,
        "angles": angles or ["angle A", "angle B", "angle C"],
        "chosen_index": chosen_index,
    }


# ---------------------------------------------------------------------------
# 1. append_entry creates file if not exists
# ---------------------------------------------------------------------------

def test_append_creates_file(isolated_history):
    assert not isolated_history.exists()
    append_entry(_entry())
    assert isolated_history.exists()


# ---------------------------------------------------------------------------
# 2. append_entry appends multiple entries correctly
# ---------------------------------------------------------------------------

def test_append_multiple_entries(isolated_history):
    e1 = _entry(timestamp="2026-03-28T10:00:00Z")
    e2 = _entry(timestamp="2026-03-28T11:00:00Z")
    append_entry(e1)
    append_entry(e2)

    lines = isolated_history.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == e1
    assert json.loads(lines[1]) == e2


# ---------------------------------------------------------------------------
# 3. get_recent_for_url returns entries for matching URL only
# ---------------------------------------------------------------------------

def test_get_recent_filters_by_url(isolated_history):
    append_entry(_entry(url="https://www.linkedin.com/in/alice"))
    append_entry(_entry(url="https://www.linkedin.com/in/bob"))
    append_entry(_entry(url="https://www.linkedin.com/in/alice"))

    results = get_recent_for_url("https://www.linkedin.com/in/alice")
    assert all(r["url"] == "https://www.linkedin.com/in/alice" for r in results)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# 4. get_recent_for_url returns most recent first (by timestamp)
# ---------------------------------------------------------------------------

def test_get_recent_for_url_most_recent_first(isolated_history):
    url = "https://www.linkedin.com/in/alice"
    append_entry(_entry(url=url, timestamp="2026-03-28T08:00:00Z"))
    append_entry(_entry(url=url, timestamp="2026-03-28T12:00:00Z"))
    append_entry(_entry(url=url, timestamp="2026-03-28T06:00:00Z"))

    results = get_recent_for_url(url)
    timestamps = [r["timestamp"] for r in results]
    assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# 5. get_recent_for_url respects limit parameter
# ---------------------------------------------------------------------------

def test_get_recent_for_url_respects_limit(isolated_history):
    url = "https://www.linkedin.com/in/alice"
    for hour in range(5):
        append_entry(_entry(url=url, timestamp=f"2026-03-28T{hour:02d}:00:00Z"))

    results = get_recent_for_url(url, limit=2)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# 6. get_recent_for_url returns empty list when no history file exists
# ---------------------------------------------------------------------------

def test_get_recent_for_url_no_file(isolated_history):
    assert not isolated_history.exists()
    results = get_recent_for_url("https://www.linkedin.com/in/alice")
    assert results == []


# ---------------------------------------------------------------------------
# 7. get_recent_for_url returns empty list when no entries match URL
# ---------------------------------------------------------------------------

def test_get_recent_for_url_no_match(isolated_history):
    append_entry(_entry(url="https://www.linkedin.com/in/bob"))
    results = get_recent_for_url("https://www.linkedin.com/in/alice")
    assert results == []


# ---------------------------------------------------------------------------
# 8. update_chosen_index updates the right entry
# ---------------------------------------------------------------------------

def test_update_chosen_index(isolated_history):
    url = "https://www.linkedin.com/in/alice"
    ts = "2026-03-28T10:00:00Z"
    append_entry(_entry(url=url, timestamp=ts, chosen_index=None))
    append_entry(_entry(url=url, timestamp="2026-03-28T11:00:00Z", chosen_index=None))

    update_chosen_index(url, ts, chosen_index=2)

    lines = isolated_history.read_text(encoding="utf-8").strip().splitlines()
    entries = [json.loads(l) for l in lines]

    target = next(e for e in entries if e["timestamp"] == ts)
    other = next(e for e in entries if e["timestamp"] != ts)

    assert target["chosen_index"] == 2
    assert other["chosen_index"] is None


# ---------------------------------------------------------------------------
# 9. update_chosen_index silently handles non-existent entry
# ---------------------------------------------------------------------------

def test_update_chosen_index_missing_entry(isolated_history):
    append_entry(_entry(url="https://www.linkedin.com/in/alice", timestamp="2026-03-28T10:00:00Z"))

    # Should not raise
    update_chosen_index(
        "https://www.linkedin.com/in/alice",
        "1999-01-01T00:00:00Z",
        chosen_index=1,
    )

    # File should be unchanged
    lines = isolated_history.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# 10. list_recent returns entries across all URLs, most recent first
# ---------------------------------------------------------------------------

def test_list_recent_all_urls_most_recent_first(isolated_history):
    append_entry(_entry(url="https://www.linkedin.com/in/alice", timestamp="2026-03-28T08:00:00Z"))
    append_entry(_entry(url="https://www.linkedin.com/in/bob",   timestamp="2026-03-28T12:00:00Z"))
    append_entry(_entry(url="https://www.linkedin.com/in/carol", timestamp="2026-03-28T06:00:00Z"))

    results = list_recent()
    timestamps = [r["timestamp"] for r in results]
    assert timestamps == sorted(timestamps, reverse=True)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# 11. list_recent respects limit parameter
# ---------------------------------------------------------------------------

def test_list_recent_respects_limit(isolated_history):
    for hour in range(10):
        append_entry(_entry(timestamp=f"2026-03-28T{hour:02d}:00:00Z"))

    results = list_recent(limit=4)
    assert len(results) == 4


# ---------------------------------------------------------------------------
# 12. Corrupt JSONL line is skipped without crashing
# ---------------------------------------------------------------------------

def test_corrupt_line_skipped(isolated_history, capsys):
    isolated_history.parent.mkdir(parents=True, exist_ok=True)
    good1 = _entry(timestamp="2026-03-28T08:00:00Z")
    good2 = _entry(timestamp="2026-03-28T10:00:00Z")

    with isolated_history.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(good1) + "\n")
        fh.write("THIS IS NOT JSON !!!\n")
        fh.write(json.dumps(good2) + "\n")

    results = list_recent()
    assert len(results) == 2

    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "corrupt" in captured.err.lower()


# ---------------------------------------------------------------------------
# 13. format_entry_summary formats correctly
# ---------------------------------------------------------------------------

def test_format_entry_summary():
    entry = _entry(
        url="https://www.linkedin.com/in/sarah-chen",
        timestamp="2026-03-28T15:30:00Z",
        persona="founder",
        target_name="Sarah Chen",
        target_role="Head of ML @ Stripe",
    )
    summary = format_entry_summary(entry)
    assert summary == "2026-03-28 | founder | Sarah Chen @ Stripe | https://www.linkedin.com/in/sarah-chen"


def test_format_entry_summary_no_at_sign():
    """When target_role has no '@', the full role is used as company."""
    entry = _entry(
        url="https://www.linkedin.com/in/joe",
        timestamp="2026-01-15T09:00:00Z",
        persona="investor",
        target_name="Joe Doe",
        target_role="Independent Consultant",
    )
    summary = format_entry_summary(entry)
    assert summary == "2026-01-15 | investor | Joe Doe @ Independent Consultant | https://www.linkedin.com/in/joe"
