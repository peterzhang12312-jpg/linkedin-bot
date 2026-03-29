"""
Tests for MessageGenerator (linkedin_bot/generator.py).

All tests mock google.genai.Client — no real API calls are made.
"""
import json
import os
from unittest.mock import MagicMock, patch, call

import pytest

from linkedin_bot.generator import MessageGenerator, DraftAngle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_response(angles: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.text = json.dumps({"angles": angles})
    return mock


CLEAN_ANGLES = [
    {
        "hook": "recent_post",
        "message": "Hi Sarah, your post on ML systems resonated. Building something similar in legal AI. Would love to swap notes — 15 mins?",
    },
    {
        "hook": "career_transition",
        "message": "Noticed your move from DeepMind to Stripe. That arc from pure research to product is rare. How are you finding the shift?",
    },
    {
        "hook": "shared_interest",
        "message": "We're both working on real-time inference at scale. Different industries but same constraints. Open to a quick call sometime?",
    },
]

# A minimal context dict that satisfies render_prompt substitutions.
SAMPLE_CONTEXT = {
    "USER_NAME": "Alex",
    "USER_BIO": "Building legal AI tools.",
    "USER_GOAL": "Expand my network in ML.",
    "USER_TONE": "direct and curious",
    "TARGET_NAME": "Sarah",
    "TARGET_ROLE": "Head of ML",
    "TARGET_COMPANY": "Stripe",
    "TARGET_LOCATION": "San Francisco, CA",
    "TARGET_BIO": "ML researcher turned product builder.",
    "TARGET_EXPERIENCE": "Head of ML at Stripe; Research Scientist at DeepMind",
    "TARGET_POSTS": "Post 1: Thoughts on real-time inference at scale.",
    "PREFERRED_ANGLES_HINT": "",
}


def make_generator() -> MessageGenerator:
    """Create a MessageGenerator without touching the environment."""
    return MessageGenerator(api_key="fake-key", model="gemini-2.0-flash")


# ---------------------------------------------------------------------------
# 1. generate() returns exactly 3 DraftAngle objects
# ---------------------------------------------------------------------------

@patch("linkedin_bot.generator.genai.Client")
def test_generate_returns_three_angles(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = make_mock_response(CLEAN_ANGLES)

    gen = make_generator()
    results = gen.generate(SAMPLE_CONTEXT)

    assert len(results) == 3


# ---------------------------------------------------------------------------
# 2. DraftAngle has correct hook, message, char_count
# ---------------------------------------------------------------------------

@patch("linkedin_bot.generator.genai.Client")
def test_draft_angle_fields(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = make_mock_response(CLEAN_ANGLES)

    gen = make_generator()
    results = gen.generate(SAMPLE_CONTEXT)

    for i, angle in enumerate(results):
        assert isinstance(angle, DraftAngle)
        assert angle.hook == CLEAN_ANGLES[i]["hook"]
        assert angle.message == CLEAN_ANGLES[i]["message"]
        assert angle.char_count == len(CLEAN_ANGLES[i]["message"])


# ---------------------------------------------------------------------------
# 3. Clean angles pass with no warnings and attempts==1
# ---------------------------------------------------------------------------

@patch("linkedin_bot.generator.genai.Client")
def test_clean_angles_no_warnings(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.return_value = make_mock_response(CLEAN_ANGLES)

    gen = make_generator()
    results = gen.generate(SAMPLE_CONTEXT)

    for angle in results:
        assert angle.warnings == []
        assert angle.attempts == 1


# ---------------------------------------------------------------------------
# 4. AI-speak in angle triggers regen (mock returns clean on second call)
# ---------------------------------------------------------------------------

@patch("linkedin_bot.generator.genai.Client")
def test_ai_speak_triggers_regen(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    dirty_angles = list(CLEAN_ANGLES)  # shallow copy list
    # Replace angle 0 with a dirty message containing "leverage"
    dirty_angles = [
        {"hook": "recent_post", "message": "We can leverage your ML expertise for our team."},
        CLEAN_ANGLES[1],
        CLEAN_ANGLES[2],
    ]
    clean_regen = list(CLEAN_ANGLES)  # all-clean response for regen

    mock_client.models.generate_content.side_effect = [
        make_mock_response(dirty_angles),   # initial call — angle 0 is dirty
        make_mock_response(clean_regen),    # regen call — angle 0 is clean this time
    ]

    gen = make_generator()
    results = gen.generate(SAMPLE_CONTEXT)

    assert len(results) == 3
    # angle 0 should now be the clean regen version
    assert results[0].warnings == []
    assert results[0].attempts == 2


# ---------------------------------------------------------------------------
# 5. 280-char overage triggers regen
# ---------------------------------------------------------------------------

@patch("linkedin_bot.generator.genai.Client")
def test_over_280_chars_triggers_regen(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    long_message = "A" * 300  # 300 chars — over limit
    dirty_angles = [
        {"hook": "recent_post", "message": long_message},
        CLEAN_ANGLES[1],
        CLEAN_ANGLES[2],
    ]
    clean_regen = list(CLEAN_ANGLES)

    mock_client.models.generate_content.side_effect = [
        make_mock_response(dirty_angles),
        make_mock_response(clean_regen),
    ]

    gen = make_generator()
    results = gen.generate(SAMPLE_CONTEXT)

    assert results[0].warnings == []
    assert results[0].attempts == 2
    assert len(results[0].message) <= 280


# ---------------------------------------------------------------------------
# 6. Regen counter exhaustion → DraftAngle has "quality check failed" in warnings
# ---------------------------------------------------------------------------

@patch("linkedin_bot.generator.genai.Client")
def test_exhausted_regen_quality_check_warning(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    long_message = "A" * 300
    always_dirty = [
        {"hook": "recent_post", "message": long_message},
        CLEAN_ANGLES[1],
        CLEAN_ANGLES[2],
    ]

    # All 3 calls return dirty angle 0
    mock_client.models.generate_content.side_effect = [
        make_mock_response(always_dirty),
        make_mock_response(always_dirty),
        make_mock_response(always_dirty),
    ]

    gen = make_generator()
    results = gen.generate(SAMPLE_CONTEXT)

    assert "quality check failed" in results[0].warnings


# ---------------------------------------------------------------------------
# 7. Regen counter exhaustion → attempts==3
# ---------------------------------------------------------------------------

@patch("linkedin_bot.generator.genai.Client")
def test_exhausted_regen_attempts_equals_3(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    long_message = "A" * 300
    always_dirty = [
        {"hook": "recent_post", "message": long_message},
        CLEAN_ANGLES[1],
        CLEAN_ANGLES[2],
    ]

    mock_client.models.generate_content.side_effect = [
        make_mock_response(always_dirty),
        make_mock_response(always_dirty),
        make_mock_response(always_dirty),
    ]

    gen = make_generator()
    results = gen.generate(SAMPLE_CONTEXT)

    assert results[0].attempts == 3


# ---------------------------------------------------------------------------
# 8. Gemini API exception → DraftAngle has "generation failed" in warnings
# ---------------------------------------------------------------------------

@patch("linkedin_bot.generator.genai.Client")
def test_api_exception_on_initial_call(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.models.generate_content.side_effect = RuntimeError("API down")

    gen = make_generator()
    results = gen.generate(SAMPLE_CONTEXT)

    for angle in results:
        assert "generation failed" in angle.warnings


# ---------------------------------------------------------------------------
# 9. Gemini API exception → other 2 angles still generated (don't abort)
# ---------------------------------------------------------------------------

@patch("linkedin_bot.generator.genai.Client")
def test_api_exception_during_regen_other_angles_still_generated(mock_client_cls):
    """
    Angle 0 is dirty on first call, then regen raises an exception.
    Angles 1 and 2 should still be generated cleanly from the first call.
    """
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    long_message = "A" * 300
    initial_angles = [
        {"hook": "recent_post", "message": long_message},
        CLEAN_ANGLES[1],
        CLEAN_ANGLES[2],
    ]

    mock_client.models.generate_content.side_effect = [
        make_mock_response(initial_angles),  # first call succeeds with dirty angle 0
        RuntimeError("API down during regen"),  # regen for angle 0 fails
    ]

    gen = make_generator()
    results = gen.generate(SAMPLE_CONTEXT)

    assert len(results) == 3
    # angle 0 gets the error
    assert "generation failed" in results[0].warnings
    # angles 1 and 2 are clean from the initial call
    assert results[1].warnings == []
    assert results[2].warnings == []


# ---------------------------------------------------------------------------
# 10. Response with invalid JSON → angle gets error warning, doesn't crash
# ---------------------------------------------------------------------------

@patch("linkedin_bot.generator.genai.Client")
def test_invalid_json_response_does_not_crash(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client

    bad_response = MagicMock()
    bad_response.text = "This is not JSON at all %%%"
    mock_client.models.generate_content.return_value = bad_response

    gen = make_generator()
    results = gen.generate(SAMPLE_CONTEXT)

    assert len(results) == 3
    for angle in results:
        assert "generation failed" in angle.warnings


# ---------------------------------------------------------------------------
# 11. _check_quality() passes clean message
# ---------------------------------------------------------------------------

def test_check_quality_passes_clean_message():
    gen = make_generator()
    passes, issues = gen._check_quality(
        "Hi Sarah, your post on ML systems resonated. Would love to swap notes — 15 mins?"
    )
    assert passes is True
    assert issues == []


# ---------------------------------------------------------------------------
# 12. _check_quality() fails message over 280 chars
# ---------------------------------------------------------------------------

def test_check_quality_fails_over_280_chars():
    gen = make_generator()
    long_msg = "A" * 281
    passes, issues = gen._check_quality(long_msg)
    assert passes is False
    assert any("exceeds 280 chars" in issue for issue in issues)


# ---------------------------------------------------------------------------
# 13. _check_quality() fails message with AI-speak
# ---------------------------------------------------------------------------

def test_check_quality_fails_ai_speak():
    gen = make_generator()
    passes, issues = gen._check_quality(
        "I wanted to touch base about a potential collaboration."
    )
    assert passes is False
    assert any("AI-speak detected" in issue for issue in issues)


# ---------------------------------------------------------------------------
# 14. _check_quality() fails message with BOTH issues — both issues returned
# ---------------------------------------------------------------------------

def test_check_quality_fails_both_issues():
    gen = make_generator()
    # Build a message that is both over 280 chars and contains AI-speak.
    ai_speak_msg = "We should leverage " + ("X" * 270)
    assert len(ai_speak_msg) > 280  # confirm it's long enough

    passes, issues = gen._check_quality(ai_speak_msg)

    assert passes is False
    char_issues = [i for i in issues if "exceeds 280 chars" in i]
    aispeak_issues = [i for i in issues if "AI-speak detected" in i]
    assert len(char_issues) == 1, f"Expected char issue, got: {issues}"
    assert len(aispeak_issues) == 1, f"Expected AI-speak issue, got: {issues}"
    assert len(issues) == 2
