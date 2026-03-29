"""
Tests for linkedin_bot.context — ContextEngine (build_context + render_prompt).
All pure Python logic; no mocking required.
"""

import pytest
from linkedin_bot.context import build_context, render_prompt


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

PERSONA = {
    "USER_NAME": "Alice Chen",
    "USER_BIO": "ML engineer turned founder. Building AI tools for lawyers.",
    "USER_GOAL": "Connect with legal-tech founders to explore partnerships.",
    "USER_TONE": "warm and direct",
}

PROFILE = {
    "name": "Bob Smith",
    "headline": "Head of ML @ Stripe",
    "location": "San Francisco, CA",
    "bio": "Passionate about machine learning at scale.",
    "experience": [
        {"title": "Head of ML", "company": "Stripe"},
        {"title": "Senior Engineer", "company": "Google"},
    ],
    "skills": ["Python", "TensorFlow", "Leadership"],
}

POSTS = [
    "Excited to announce our new ML platform launch!",
    "Thoughts on scaling transformers in production...",
    "Great conversation at NeurIPS this week.",
    "Why I left big tech to join a startup.",
    "The future of AI in finance.",
]


# ---------------------------------------------------------------------------
# 1. Full context built correctly with all profile fields and 5 posts
# ---------------------------------------------------------------------------

def test_full_context_all_fields():
    ctx = build_context(PROFILE, POSTS, PERSONA)

    assert ctx["USER_NAME"] == "Alice Chen"
    assert ctx["USER_BIO"] == PERSONA["USER_BIO"]
    assert ctx["USER_GOAL"] == PERSONA["USER_GOAL"]
    assert ctx["USER_TONE"] == "warm and direct"

    assert ctx["TARGET_NAME"] == "Bob Smith"
    assert ctx["TARGET_ROLE"] == "Head of ML"
    assert ctx["TARGET_COMPANY"] == "Stripe"
    assert ctx["TARGET_LOCATION"] == "San Francisco, CA"
    assert ctx["TARGET_BIO"] == "Passionate about machine learning at scale."
    assert "Head of ML at Stripe" in ctx["TARGET_EXPERIENCE"]
    assert ctx["TARGET_POSTS"] != ""


# ---------------------------------------------------------------------------
# 2. Posts formatted correctly: "Post 1: ...\n\nPost 2: ..."
# ---------------------------------------------------------------------------

def test_posts_formatted_correctly():
    ctx = build_context(PROFILE, POSTS[:2], PERSONA)
    expected = "Post 1: Excited to announce our new ML platform launch!\n\nPost 2: Thoughts on scaling transformers in production..."
    assert ctx["TARGET_POSTS"] == expected


# ---------------------------------------------------------------------------
# 3. Empty posts list → TARGET_POSTS is empty string
# ---------------------------------------------------------------------------

def test_empty_posts_returns_empty_string():
    ctx = build_context(PROFILE, [], PERSONA)
    assert ctx["TARGET_POSTS"] == ""


# ---------------------------------------------------------------------------
# 4. Posts truncated at 500 chars
# ---------------------------------------------------------------------------

def test_posts_truncated_at_500_chars():
    long_post = "x" * 600
    ctx = build_context(PROFILE, [long_post], PERSONA)
    # Should be truncated: first 500 chars + "..."
    expected_post_text = "x" * 500 + "..."
    assert ctx["TARGET_POSTS"] == f"Post 1: {expected_post_text}"


def test_posts_not_truncated_when_under_500():
    short_post = "y" * 499
    ctx = build_context(PROFILE, [short_post], PERSONA)
    # Should NOT have "..." appended
    assert ctx["TARGET_POSTS"] == f"Post 1: {'y' * 499}"
    assert not ctx["TARGET_POSTS"].endswith("...")


# ---------------------------------------------------------------------------
# 5. Headline split: "Head of ML @ Stripe" → role="Head of ML", company="Stripe"
# ---------------------------------------------------------------------------

def test_headline_split_standard():
    profile = {**PROFILE, "headline": "Head of ML @ Stripe"}
    ctx = build_context(profile, [], PERSONA)
    assert ctx["TARGET_ROLE"] == "Head of ML"
    assert ctx["TARGET_COMPANY"] == "Stripe"


# ---------------------------------------------------------------------------
# 6. Headline with no "@" → role=headline, company=""
# ---------------------------------------------------------------------------

def test_headline_no_at_sign():
    profile = {**PROFILE, "headline": "CTO"}
    ctx = build_context(profile, [], PERSONA)
    assert ctx["TARGET_ROLE"] == "CTO"
    assert ctx["TARGET_COMPANY"] == ""


# ---------------------------------------------------------------------------
# 7. Headline with multiple "@" → split on first "@" only
# ---------------------------------------------------------------------------

def test_headline_multiple_at_signs():
    profile = {**PROFILE, "headline": "CTO @ Acme @ Division"}
    ctx = build_context(profile, [], PERSONA)
    assert ctx["TARGET_ROLE"] == "CTO"
    assert ctx["TARGET_COMPANY"] == "Acme @ Division"


# ---------------------------------------------------------------------------
# 8. Missing bio in profile_data → TARGET_BIO is empty string (no KeyError)
# ---------------------------------------------------------------------------

def test_missing_bio_no_keyerror():
    profile = {k: v for k, v in PROFILE.items() if k != "bio"}
    ctx = build_context(profile, [], PERSONA)
    assert ctx["TARGET_BIO"] == ""


# ---------------------------------------------------------------------------
# 9. Missing location in profile_data → TARGET_LOCATION is empty string
# ---------------------------------------------------------------------------

def test_missing_location_no_keyerror():
    profile = {k: v for k, v in PROFILE.items() if k != "location"}
    ctx = build_context(profile, [], PERSONA)
    assert ctx["TARGET_LOCATION"] == ""


# ---------------------------------------------------------------------------
# 10. preferred_angles in persona → PREFERRED_ANGLES_HINT contains ordered list
# ---------------------------------------------------------------------------

def test_preferred_angles_hint_present():
    persona = {
        **PERSONA,
        "preferred_angles": ["recent_post", "career_transition", "shared_interest"],
    }
    ctx = build_context(PROFILE, [], persona)
    hint = ctx["PREFERRED_ANGLES_HINT"]
    assert "recent_post" in hint
    assert "career_transition" in hint
    assert "shared_interest" in hint
    # Order is preserved in the hint string
    assert hint.index("recent_post") < hint.index("career_transition") < hint.index("shared_interest")


# ---------------------------------------------------------------------------
# 11. preferred_angles absent in persona → PREFERRED_ANGLES_HINT is empty string
# ---------------------------------------------------------------------------

def test_preferred_angles_hint_absent():
    # PERSONA fixture has no preferred_angles key
    ctx = build_context(PROFILE, [], PERSONA)
    assert ctx["PREFERRED_ANGLES_HINT"] == ""


# ---------------------------------------------------------------------------
# 12. render_prompt() replaces {{USER_NAME}} correctly
# ---------------------------------------------------------------------------

def test_render_prompt_replaces_key():
    template = "Hi, I'm {{USER_NAME}} and I want to connect."
    context = {"USER_NAME": "Alice Chen"}
    result = render_prompt(template, context)
    assert result == "Hi, I'm Alice Chen and I want to connect."


# ---------------------------------------------------------------------------
# 13. render_prompt() leaves unknown {{UNKNOWN_KEY}} as-is
# ---------------------------------------------------------------------------

def test_render_prompt_unknown_key_left_intact():
    template = "Hello {{TARGET_NAME}}, also {{UNKNOWN_KEY}}."
    context = {"TARGET_NAME": "Bob"}
    result = render_prompt(template, context)
    assert result == "Hello Bob, also {{UNKNOWN_KEY}}."


# ---------------------------------------------------------------------------
# 14. render_prompt() handles context with empty string values
# ---------------------------------------------------------------------------

def test_render_prompt_empty_string_value():
    template = "Company: {{TARGET_COMPANY}}."
    context = {"TARGET_COMPANY": ""}
    result = render_prompt(template, context)
    assert result == "Company: ."


# ---------------------------------------------------------------------------
# 15. Up to 5 posts used even if 7 provided
# ---------------------------------------------------------------------------

def test_max_five_posts_from_seven():
    seven_posts = [f"Post content number {i}" for i in range(1, 8)]
    ctx = build_context(PROFILE, seven_posts, PERSONA)
    # Only Posts 1-5 should appear; "Post 6:" should not exist
    assert "Post 5:" in ctx["TARGET_POSTS"]
    assert "Post 6:" not in ctx["TARGET_POSTS"]
