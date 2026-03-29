"""
AI-speak risk scanner for LinkedIn message drafts.

Deterministic keyword blocklist — checks for generic, robotic phrases
that signal AI-generated content and reduce message authenticity.
"""

BLOCKED_PHRASES = [
    "hope this finds you",
    "touch base",
    "circle back",
    "reach out",
    "leverage",
    "synergy",
    "synergies",
    "excited to connect",
    "let's connect",
    "i wanted to reach out",
    "value add",
    "thought leader",
    "game changer",
    "per my last email",
    "picking your brain",
]


def scan(message: str) -> tuple[bool, list[str]]:
    """
    Scan a message draft for AI-speak blocked phrases.

    Args:
        message: The message text to scan.

    Returns:
        A tuple of (is_clean, matched_phrases) where:
        - is_clean is True if no blocked phrases were found (safe to send)
        - is_clean is False if one or more blocked phrases were found (needs regen)
        - matched_phrases is a list of the blocked phrases that were found
    """
    lowered = message.lower()
    matches = [phrase for phrase in BLOCKED_PHRASES if phrase in lowered]
    is_clean = len(matches) == 0
    return is_clean, matches
