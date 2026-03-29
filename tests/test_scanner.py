"""
Tests for the AI-speak risk scanner (linkedin_bot/scanner.py).
"""

import pytest
from linkedin_bot.scanner import scan, BLOCKED_PHRASES


# ---------------------------------------------------------------------------
# 1. Clean message passes
# ---------------------------------------------------------------------------

def test_clean_message_no_matches():
    clean, matches = scan("Hi Sarah, I saw your post on ML systems and found it insightful.")
    assert clean is True
    assert matches == []


def test_clean_message_professional_tone():
    clean, matches = scan("Your work on distributed systems caught my attention — would love to hear more.")
    assert clean is True
    assert matches == []


# ---------------------------------------------------------------------------
# 2. Individual blocked phrases — at least 5 specific phrases
# ---------------------------------------------------------------------------

def test_hope_this_finds_you():
    clean, matches = scan("Hope this finds you well and thriving.")
    assert clean is False
    assert "hope this finds you" in matches


def test_touch_base():
    clean, matches = scan("I wanted to touch base about the project.")
    assert clean is False
    assert "touch base" in matches


def test_circle_back():
    clean, matches = scan("Let's circle back on this next week.")
    assert clean is False
    assert "circle back" in matches


def test_leverage():
    clean, matches = scan("We can leverage this opportunity.")
    assert clean is False
    assert "leverage" in matches


def test_synergy():
    clean, matches = scan("There is real synergy between our teams.")
    assert clean is False
    assert "synergy" in matches


def test_synergies():
    clean, matches = scan("We can unlock synergies across both orgs.")
    assert clean is False
    assert "synergies" in matches


def test_excited_to_connect():
    clean, matches = scan("I'm excited to connect with you!")
    assert clean is False
    assert "excited to connect" in matches


def test_lets_connect():
    clean, matches = scan("Let's connect and explore collaboration.")
    assert clean is False
    assert "let's connect" in matches


def test_i_wanted_to_reach_out():
    clean, matches = scan("I wanted to reach out because I admire your work.")
    assert clean is False
    assert "i wanted to reach out" in matches


def test_value_add():
    clean, matches = scan("This would be a real value add for the team.")
    assert clean is False
    assert "value add" in matches


def test_thought_leader():
    clean, matches = scan("You are a genuine thought leader in this space.")
    assert clean is False
    assert "thought leader" in matches


def test_game_changer():
    clean, matches = scan("This technology is a total game changer.")
    assert clean is False
    assert "game changer" in matches


def test_per_my_last_email():
    clean, matches = scan("Per my last email, the deadline is Friday.")
    assert clean is False
    assert "per my last email" in matches


def test_picking_your_brain():
    clean, matches = scan("I'd love to spend time picking your brain on this.")
    assert clean is False
    assert "picking your brain" in matches


def test_reach_out():
    clean, matches = scan("Feel free to reach out anytime.")
    assert clean is False
    assert "reach out" in matches


# ---------------------------------------------------------------------------
# 3. Case-insensitive matching
# ---------------------------------------------------------------------------

def test_uppercase_leverage():
    clean, matches = scan("We should LEVERAGE this trend immediately.")
    assert clean is False
    assert "leverage" in matches


def test_mixed_case_synergy():
    clean, matches = scan("The Synergy between teams is undeniable.")
    assert clean is False
    assert "synergy" in matches


def test_all_caps_touch_base():
    clean, matches = scan("WE NEED TO TOUCH BASE ASAP.")
    assert clean is False
    assert "touch base" in matches


def test_mixed_case_thought_leader():
    clean, matches = scan("She is a Thought Leader in AI ethics.")
    assert clean is False
    assert "thought leader" in matches


# ---------------------------------------------------------------------------
# 4. Partial match — substring inside a longer word
# ---------------------------------------------------------------------------

def test_leveraging_triggers_leverage():
    # "leveraging" does not contain the substring "leverage" (ends in "e", not "ing")
    # The scanner checks if the blocked phrase is a substring of the message,
    # so "leverage" must appear verbatim. "leveraging" is a safe word.
    clean, matches = scan("I'm interested in leveraging new tools.")
    assert clean is True
    assert matches == []


def test_leveraged_triggers_leverage():
    clean, matches = scan("We leveraged their platform heavily.")
    assert clean is False
    assert "leverage" in matches


def test_synergistic_triggers_synergy():
    # "synergy" is a substring of "synergistic"? No — but "synergies" is separate.
    # "synergistic" does NOT contain "synergy" as a substring.
    # This confirms the scanner won't over-match "synergistic".
    clean, matches = scan("The synergistic effect was obvious.")
    assert clean is True
    assert matches == []


def test_reaching_out_triggers_reach_out():
    # "reaching out" contains the substring "reach" but not "reach out" (no space separation needed —
    # "reaching out" does contain "reach" + space + "out"? Let's be precise:
    # "reaching out" = r-e-a-c-h-i-n-g- -o-u-t — "reach out" = r-e-a-c-h- -o-u-t
    # "reaching out" does NOT contain "reach out" as a substring (has "reaching" not "reach ")
    clean, matches = scan("I've been reaching out to many folks.")
    assert clean is True
    assert matches == []


# ---------------------------------------------------------------------------
# 5. Multiple phrases in one message — all returned
# ---------------------------------------------------------------------------

def test_multiple_phrases_all_returned():
    # "i wanted to reach out" matches; "leveraging" does not match "leverage";
    # "synergies" matches exactly; "reach out" is a substring of "reach out about"
    msg = "I wanted to reach out about leveraging synergies between our teams."
    clean, matches = scan(msg)
    assert clean is False
    assert "i wanted to reach out" in matches
    assert "reach out" in matches
    assert "synergies" in matches
    assert "leverage" not in matches


def test_two_phrases_returned():
    msg = "Hope this finds you well — let's connect soon."
    clean, matches = scan(msg)
    assert clean is False
    assert "hope this finds you" in matches
    assert "let's connect" in matches
    assert len(matches) == 2


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------

def test_empty_string():
    clean, matches = scan("")
    assert clean is True
    assert matches == []


def test_whitespace_only():
    clean, matches = scan("   ")
    assert clean is True
    assert matches == []


def test_single_word_no_match():
    clean, matches = scan("hello")
    assert clean is True
    assert matches == []


# ---------------------------------------------------------------------------
# 7. Phrase position — start of message
# ---------------------------------------------------------------------------

def test_phrase_at_start():
    clean, matches = scan("Hope this finds you in good health.")
    assert clean is False
    assert "hope this finds you" in matches


def test_touch_base_at_start():
    clean, matches = scan("Touch base with me when you get a chance.")
    assert clean is False
    assert "touch base" in matches


# ---------------------------------------------------------------------------
# 8. Phrase position — end of message
# ---------------------------------------------------------------------------

def test_phrase_at_end():
    clean, matches = scan("Looking forward to hearing your thoughts on leverage.")
    assert clean is False
    assert "leverage" in matches


def test_reach_out_at_end():
    clean, matches = scan("Don't hesitate to reach out.")
    assert clean is False
    assert "reach out" in matches


# ---------------------------------------------------------------------------
# 9. Phrase position — middle of message
# ---------------------------------------------------------------------------

def test_phrase_in_middle():
    clean, matches = scan("As we discussed, the synergy we have is rare, and I appreciate it.")
    assert clean is False
    assert "synergy" in matches


def test_thought_leader_in_middle():
    clean, matches = scan("Many consider her a thought leader in this niche, which is well-deserved.")
    assert clean is False
    assert "thought leader" in matches


# ---------------------------------------------------------------------------
# 10. Adjacent similar words that do NOT contain blocked phrases
# ---------------------------------------------------------------------------

def test_touchstone_does_not_match_touch_base():
    clean, matches = scan("This is a touchstone moment for the industry.")
    assert clean is True
    assert matches == []


def test_reaching_does_not_match_reach_out_alone():
    # "reach out" as a phrase — "reaching" alone does not contain "reach out"
    clean, matches = scan("I'm reaching new heights in my career.")
    assert clean is True
    assert matches == []


def test_synergistic_does_not_match():
    clean, matches = scan("The synergistic approach worked well.")
    assert clean is True
    assert matches == []


def test_game_does_not_match_game_changer():
    clean, matches = scan("She brought her A-game to the presentation.")
    assert clean is True
    assert matches == []


def test_circle_does_not_match_circle_back():
    clean, matches = scan("The circle of trust is small.")
    assert clean is True
    assert matches == []


def test_base_does_not_match_touch_base():
    clean, matches = scan("Let's cover the base case first.")
    assert clean is True
    assert matches == []


# ---------------------------------------------------------------------------
# 11. BLOCKED_PHRASES export
# ---------------------------------------------------------------------------

def test_blocked_phrases_is_exported():
    assert isinstance(BLOCKED_PHRASES, list)
    assert len(BLOCKED_PHRASES) > 0


def test_blocked_phrases_contains_expected_entries():
    assert "leverage" in BLOCKED_PHRASES
    assert "synergy" in BLOCKED_PHRASES
    assert "touch base" in BLOCKED_PHRASES
    assert "hope this finds you" in BLOCKED_PHRASES
    assert "thought leader" in BLOCKED_PHRASES
