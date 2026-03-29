"""
ContextEngine — merges scraped profile data, recent posts, and persona config
into a single context dict for prompt template rendering.

Data flow:
  profile_data (dict) + posts (list[str]) + persona (dict) → context (dict)

  context keys:
    USER_NAME, USER_BIO, USER_GOAL, USER_TONE  ← from persona
    TARGET_NAME, TARGET_ROLE, TARGET_COMPANY   ← from profile_data
    TARGET_LOCATION, TARGET_BIO, TARGET_EXPERIENCE ← from profile_data
    TARGET_POSTS                                ← formatted from posts list
    PREFERRED_ANGLES_HINT                       ← from persona (optional)
"""

import re


def _split_headline(headline: str) -> tuple[str, str]:
    """
    Split a LinkedIn headline into (role, company) on the first " @ ".

    "Head of ML @ Stripe"          → ("Head of ML", "Stripe")
    "CTO @ Acme @ Division"        → ("CTO", "Acme @ Division")
    "CTO"                          → ("CTO", "")
    """
    if " @ " in headline:
        idx = headline.index(" @ ")
        role = headline[:idx].strip()
        company = headline[idx + 3:].strip()
        return role, company
    return headline.strip(), ""


def _format_posts(posts: list[str]) -> str:
    """
    Format up to 5 posts as:
      "Post 1: {text}\n\nPost 2: {text}\n..."

    Each post is truncated to 500 characters.
    Returns empty string if posts is empty.
    """
    if not posts:
        return ""

    truncated = [
        post[:500] + "..." if len(post) > 500 else post
        for post in posts[:5]
    ]
    return "\n\n".join(f"Post {i + 1}: {text}" for i, text in enumerate(truncated))


def _format_experience(experience) -> str:
    """
    Convert an experience list to a readable string.
    Handles list of dicts or list of strings gracefully.
    Returns empty string for None / empty / unexpected types.
    """
    if not experience:
        return ""
    if isinstance(experience, str):
        return experience
    if not isinstance(experience, list):
        return ""

    parts = []
    for item in experience:
        if isinstance(item, dict):
            title = item.get("title", "")
            company = item.get("company", "")
            if title and company:
                parts.append(f"{title} at {company}")
            elif title:
                parts.append(title)
            elif company:
                parts.append(company)
            else:
                # Fallback: join all non-empty values
                parts.append(", ".join(str(v) for v in item.values() if v))
        elif isinstance(item, str):
            parts.append(item)

    return "; ".join(filter(None, parts))


def build_context(
    profile_data: dict,
    posts: list[str],
    persona: dict,
) -> dict:
    """
    Build context dict for prompt rendering.

    profile_data keys expected: name, headline, location, bio, experience (list), skills (list)
    persona keys expected: USER_NAME, USER_BIO, USER_GOAL, USER_TONE (required)
                          name, preferred_angles (optional)
    posts: list of post text strings, may be empty

    Returns dict with all template variable keys filled in.
    Missing/None values in profile_data become empty strings (never KeyError).

    TARGET_ROLE and TARGET_COMPANY are split from headline:
      "Head of ML @ Stripe" → role="Head of ML", company="Stripe"
      "CTO" → role="CTO", company=""

    TARGET_POSTS: If posts is empty, returns empty string (caller handles degrade).
      If posts available, format as:
        "Post 1: {text}\\n\\nPost 2: {text}\\n..." (up to 5 posts)
      Truncate each post to 500 chars to avoid token bloat.

    PREFERRED_ANGLES_HINT: If persona has preferred_angles list, returns:
      "Prioritize these angle types in this order: recent_post, career_transition, shared_interest.
       Generate each of the 3 angles using a different angle type from this list."
      If not present, returns empty string.
    """
    # --- Persona fields (required — assume already validated by personas.py) ---
    user_name = persona["USER_NAME"]
    user_bio = persona["USER_BIO"]
    user_goal = persona["USER_GOAL"]
    user_tone = persona["USER_TONE"]

    # --- Profile fields (all optional — missing/None → empty string) ---
    safe = lambda key: (profile_data.get(key) or "")

    headline = safe("headline")
    target_role, target_company = _split_headline(headline) if headline else ("", "")

    # --- Posts ---
    target_posts = _format_posts(posts or [])

    # --- Experience ---
    experience_raw = profile_data.get("experience")
    target_experience = _format_experience(experience_raw)

    # --- Preferred angles hint ---
    preferred_angles = persona.get("preferred_angles")
    if preferred_angles and isinstance(preferred_angles, list) and len(preferred_angles) > 0:
        angles_str = ", ".join(preferred_angles)
        preferred_angles_hint = (
            f"Prioritize these angle types in this order: {angles_str}.\n"
            f"Generate each of the {len(preferred_angles)} angles using a different angle type from this list."
        )
    else:
        preferred_angles_hint = ""

    return {
        # User / sender
        "USER_NAME": user_name,
        "USER_BIO": user_bio,
        "USER_GOAL": user_goal,
        "USER_TONE": user_tone,
        # Target / recipient
        "TARGET_NAME": safe("name"),
        "TARGET_ROLE": target_role,
        "TARGET_COMPANY": target_company,
        "TARGET_LOCATION": safe("location"),
        "TARGET_BIO": safe("bio"),
        "TARGET_EXPERIENCE": target_experience,
        # Posts
        "TARGET_POSTS": target_posts,
        # Hints
        "PREFERRED_ANGLES_HINT": preferred_angles_hint,
    }


def render_prompt(template: str, context: dict) -> str:
    """
    Replace {{KEY}} placeholders in template string with context values.
    Unknown keys in template are left as-is (no error).
    """
    def replacer(match: re.Match) -> str:
        key = match.group(1)
        if key in context:
            return str(context[key])
        # Unknown key — leave the placeholder intact
        return match.group(0)

    return re.sub(r"\{\{(\w+)\}\}", replacer, template)
