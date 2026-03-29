"""Tests for cli.py — Typer CLI integration layer."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

# ---------------------------------------------------------------------------
# The app under test
# ---------------------------------------------------------------------------
from cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_PROFILE = {
    "name": "Sarah Chen",
    "headline": "Head of ML @ Stripe",
    "location": "San Francisco, CA",
    "bio": "ML engineer turned product thinker.",
    "experience": [],
}

SAMPLE_POSTS = ["Post about ML systems and scaling challenges."]

SAMPLE_PERSONA = {
    "USER_NAME": "Test User",
    "USER_BIO": "Building things in legal AI.",
    "USER_GOAL": "Connect with ML engineers.",
    "USER_TONE": "concise and direct",
    "preferred_angles": ["recent_post", "career_transition", "shared_interest"],
}


def _make_angle(hook: str, message: str, warnings: list[str] | None = None):
    """Build a mock DraftAngle-like object."""
    angle = MagicMock()
    angle.hook = hook
    angle.message = message
    angle.char_count = len(message)
    angle.warnings = warnings or []
    return angle


CLEAN_ANGLES = [
    _make_angle("recent_post", "Hi Sarah, your ML post resonated. Would love to connect."),
    _make_angle("career_transition", "Noticed your move to Stripe — fascinating pivot."),
    _make_angle("shared_interest", "Both deep in AI infrastructure. 15 mins?"),
]

ALL_FAILED_ANGLES = [
    _make_angle("error", "[ERROR: generation failed]", warnings=["generation failed"]),
    _make_angle("error", "[ERROR: generation failed]", warnings=["generation failed"]),
    _make_angle("error", "[ERROR: generation failed]", warnings=["generation failed"]),
]


def _make_scraper_mock(profile_data=None, posts=None):
    """Return a pre-configured mock LinkedInScraper context manager."""
    mock_scraper = MagicMock()
    mock_scraper.__enter__ = MagicMock(return_value=mock_scraper)
    mock_scraper.__exit__ = MagicMock(return_value=False)
    mock_scraper.scrape_profile.return_value = profile_data or SAMPLE_PROFILE
    mock_scraper.scrape_recent_posts.return_value = posts if posts is not None else SAMPLE_POSTS
    return mock_scraper


# ---------------------------------------------------------------------------
# personas list
# ---------------------------------------------------------------------------

def test_personas_list_shows_both():
    with patch("linkedin_bot.personas.list_personas", return_value=["developer", "founder"]):
        result = runner.invoke(app, ["personas", "list"])
    assert result.exit_code == 0
    assert "developer" in result.output
    assert "founder" in result.output
    assert "Available personas:" in result.output


# ---------------------------------------------------------------------------
# personas new
# ---------------------------------------------------------------------------

def test_personas_new_creates_file_and_prints_path():
    fake_path = MagicMock()
    fake_path.__str__ = MagicMock(return_value="personas/developer2.json")

    with patch("linkedin_bot.personas.create_template", return_value=fake_path) as mock_create:
        result = runner.invoke(app, ["personas", "new", "developer2"])

    assert result.exit_code == 0
    mock_create.assert_called_once_with("developer2")
    assert "developer2" in result.output


def test_personas_new_file_exists_prints_error_exits_1():
    with patch(
        "linkedin_bot.personas.create_template",
        side_effect=FileExistsError("Persona file already exists: personas/developer2.json."),
    ):
        result = runner.invoke(app, ["personas", "new", "developer2"])

    assert result.exit_code == 1
    assert "Error" in result.output or "already exists" in result.output


# ---------------------------------------------------------------------------
# history show
# ---------------------------------------------------------------------------

HISTORY_ENTRY = {
    "url": "https://www.linkedin.com/in/sarahchen",
    "timestamp": "2026-03-28T15:00:00Z",
    "persona": "founder",
    "target_name": "Sarah Chen",
    "target_role": "Head of ML @ Stripe",
    "angles": ["msg1", "msg2", "msg3"],
    "chosen_index": None,
}


def test_history_show_with_history_shows_entries():
    with patch("linkedin_bot.history.get_recent_for_url", return_value=[HISTORY_ENTRY]):
        with patch(
            "linkedin_bot.history.format_entry_summary",
            return_value="2026-03-28 | founder | Sarah Chen @ Stripe | https://www.linkedin.com/in/sarahchen",
        ):
            result = runner.invoke(
                app,
                ["history", "show", "--url", "https://www.linkedin.com/in/sarahchen"],
            )

    assert result.exit_code == 0
    assert "Sarah Chen" in result.output


def test_history_show_no_history_shows_message():
    with patch("linkedin_bot.history.get_recent_for_url", return_value=[]):
        result = runner.invoke(
            app,
            ["history", "show", "--url", "https://www.linkedin.com/in/nobody"],
        )

    assert result.exit_code == 0
    assert "No history" in result.output


# ---------------------------------------------------------------------------
# history list
# ---------------------------------------------------------------------------

def test_history_list_calls_list_recent_and_displays():
    with patch("linkedin_bot.history.list_recent", return_value=[HISTORY_ENTRY]) as mock_list:
        with patch(
            "linkedin_bot.history.format_entry_summary",
            return_value="2026-03-28 | founder | Sarah Chen @ Stripe | https://...",
        ):
            result = runner.invoke(app, ["history", "list"])

    assert result.exit_code == 0
    mock_list.assert_called_once()
    assert "Sarah Chen" in result.output


# ---------------------------------------------------------------------------
# run --dry-run happy path
# ---------------------------------------------------------------------------

def test_run_dry_run_happy_path():
    mock_scraper = _make_scraper_mock()

    with patch("linkedin_bot.personas.load", return_value=SAMPLE_PERSONA), \
         patch("linkedin_bot.history.get_recent_for_url", return_value=[]), \
         patch("cli.LinkedInScraper", return_value=mock_scraper), \
         patch("cli.build_context", return_value={"ctx": "data"}), \
         patch("cli.MessageGenerator") as MockGenerator, \
         patch("pyperclip.copy") as mock_copy, \
         patch("linkedin_bot.history.append_entry"):

        mock_gen_instance = MagicMock()
        mock_gen_instance.generate.return_value = CLEAN_ANGLES
        MockGenerator.return_value = mock_gen_instance

        result = runner.invoke(
            app,
            ["run", "--url", "https://www.linkedin.com/in/sarahchen", "--dry-run"],
            input="1\n",
        )

    assert result.exit_code == 0, result.output
    assert "Message copied to clipboard" in result.output
    mock_copy.assert_called_once_with(CLEAN_ANGLES[0].message)


# ---------------------------------------------------------------------------
# run --dry-run --no-history
# ---------------------------------------------------------------------------

def test_run_dry_run_no_history():
    mock_scraper = _make_scraper_mock()

    with patch("linkedin_bot.personas.load", return_value=SAMPLE_PERSONA), \
         patch("cli.LinkedInScraper", return_value=mock_scraper), \
         patch("cli.build_context", return_value={}), \
         patch("cli.MessageGenerator") as MockGenerator, \
         patch("pyperclip.copy"), \
         patch("linkedin_bot.history.get_recent_for_url") as mock_get, \
         patch("linkedin_bot.history.append_entry") as mock_append:

        mock_gen_instance = MagicMock()
        mock_gen_instance.generate.return_value = CLEAN_ANGLES
        MockGenerator.return_value = mock_gen_instance

        result = runner.invoke(
            app,
            [
                "run",
                "--url",
                "https://www.linkedin.com/in/sarahchen",
                "--dry-run",
                "--no-history",
            ],
            input="1\n",
        )

    assert result.exit_code == 0, result.output
    mock_get.assert_not_called()
    mock_append.assert_not_called()


# ---------------------------------------------------------------------------
# run with LinkedInCaptchaError
# ---------------------------------------------------------------------------

def test_run_captcha_error_exits_1():
    from linkedin_bot.scraper import LinkedInCaptchaError

    mock_scraper = _make_scraper_mock()
    mock_scraper.scrape_profile.side_effect = LinkedInCaptchaError("CAPTCHA detected")

    with patch("linkedin_bot.personas.load", return_value=SAMPLE_PERSONA), \
         patch("linkedin_bot.history.get_recent_for_url", return_value=[]), \
         patch("cli.LinkedInScraper", return_value=mock_scraper):

        result = runner.invoke(
            app,
            ["run", "--url", "https://www.linkedin.com/in/sarahchen", "--dry-run"],
        )

    assert result.exit_code == 1
    assert "CAPTCHA" in result.output


# ---------------------------------------------------------------------------
# run with LinkedInSessionExpiredError
# ---------------------------------------------------------------------------

def test_run_session_expired_exits_1():
    from linkedin_bot.scraper import LinkedInSessionExpiredError

    mock_scraper = _make_scraper_mock()
    mock_scraper.scrape_profile.side_effect = LinkedInSessionExpiredError("Session expired")

    with patch("linkedin_bot.personas.load", return_value=SAMPLE_PERSONA), \
         patch("linkedin_bot.history.get_recent_for_url", return_value=[]), \
         patch("cli.LinkedInScraper", return_value=mock_scraper):

        result = runner.invoke(
            app,
            ["run", "--url", "https://www.linkedin.com/in/sarahchen", "--dry-run"],
        )

    assert result.exit_code == 1
    assert "session expired" in result.output.lower() or "Session" in result.output


# ---------------------------------------------------------------------------
# run with PersonaValidationError
# ---------------------------------------------------------------------------

def test_run_persona_validation_error_exits_1():
    from linkedin_bot.personas import PersonaValidationError

    with patch(
        "linkedin_bot.personas.load",
        side_effect=PersonaValidationError("Missing USER_NAME field"),
    ):
        result = runner.invoke(
            app,
            ["run", "--url", "https://www.linkedin.com/in/sarahchen", "--dry-run"],
        )

    assert result.exit_code == 1
    assert "Persona validation error" in result.output or "Missing" in result.output


# ---------------------------------------------------------------------------
# run --verbose shows scraped profile data
# ---------------------------------------------------------------------------

def test_run_verbose_shows_profile_data():
    mock_scraper = _make_scraper_mock()

    with patch("linkedin_bot.personas.load", return_value=SAMPLE_PERSONA), \
         patch("linkedin_bot.history.get_recent_for_url", return_value=[]), \
         patch("cli.LinkedInScraper", return_value=mock_scraper), \
         patch("cli.build_context", return_value={}), \
         patch("cli.MessageGenerator") as MockGenerator, \
         patch("pyperclip.copy"), \
         patch("linkedin_bot.history.append_entry"):

        mock_gen_instance = MagicMock()
        mock_gen_instance.generate.return_value = CLEAN_ANGLES
        MockGenerator.return_value = mock_gen_instance

        result = runner.invoke(
            app,
            [
                "run",
                "--url",
                "https://www.linkedin.com/in/sarahchen",
                "--dry-run",
                "--verbose",
            ],
            input="1\n",
        )

    assert result.exit_code == 0, result.output
    # Verbose mode should print profile data — check for the name or "Scraped profile"
    assert "Sarah Chen" in result.output or "Scraped profile" in result.output


# ---------------------------------------------------------------------------
# run without --verbose does NOT print debug output
# ---------------------------------------------------------------------------

def test_run_no_verbose_omits_debug_output():
    mock_scraper = _make_scraper_mock()

    with patch("linkedin_bot.personas.load", return_value=SAMPLE_PERSONA), \
         patch("linkedin_bot.history.get_recent_for_url", return_value=[]), \
         patch("cli.LinkedInScraper", return_value=mock_scraper), \
         patch("cli.build_context", return_value={}), \
         patch("cli.MessageGenerator") as MockGenerator, \
         patch("pyperclip.copy"), \
         patch("linkedin_bot.history.append_entry"):

        mock_gen_instance = MagicMock()
        mock_gen_instance.generate.return_value = CLEAN_ANGLES
        MockGenerator.return_value = mock_gen_instance

        result = runner.invoke(
            app,
            ["run", "--url", "https://www.linkedin.com/in/sarahchen", "--dry-run"],
            input="1\n",
        )

    assert result.exit_code == 0, result.output
    assert "Scraped profile:" not in result.output
    assert "Posts scraped:" not in result.output
