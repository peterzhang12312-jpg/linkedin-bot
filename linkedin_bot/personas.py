"""Persona loader module for the LinkedIn networking bot.

Personas are JSON files stored in ./personas/ directory relative to the
working directory. Each persona configures the bot's identity and tone
for outreach message generation.
"""

import json
from pathlib import Path

PERSONAS_DIR = Path("personas")

REQUIRED_FIELDS = ["USER_NAME", "USER_BIO", "USER_GOAL", "USER_TONE"]

TEMPLATE = {
    "name": "YOUR_PERSONA_NAME",
    "USER_NAME": "YOUR_FULL_NAME",
    "USER_BIO": "YOUR_BACKGROUND_IN_2_SENTENCES",
    "USER_GOAL": "WHAT_YOU_ARE_TRYING_TO_ACHIEVE_WITH_THIS_OUTREACH",
    "USER_TONE": "concise and direct",
    "preferred_angles": ["recent_post", "career_transition", "shared_interest"],
}


class PersonaValidationError(Exception):
    """Raised when a persona file is missing required fields or is invalid JSON."""
    pass


def load(name: str) -> dict:
    """Load persona by name (without .json extension).

    Args:
        name: Persona name, e.g. "founder" for personas/founder.json.

    Returns:
        The full persona dict.

    Raises:
        FileNotFoundError: If the persona file does not exist.
        PersonaValidationError: If the file contains invalid JSON or is missing
            one or more required fields.
    """
    persona_path = PERSONAS_DIR / f"{name}.json"

    if not persona_path.exists():
        raise FileNotFoundError(
            f"Persona file not found: {persona_path}. "
            f"Run: python cli.py personas new {name}"
        )

    try:
        text = persona_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PersonaValidationError(
            f"Persona '{name}' contains invalid JSON: {exc}. "
            f"Run: python cli.py personas new {name}"
        ) from exc

    for field in REQUIRED_FIELDS:
        if field not in data:
            raise PersonaValidationError(
                f"Persona '{name}' is missing required field: {field}. "
                f"Run: python cli.py personas new {name}"
            )

    return data


def list_personas() -> list[str]:
    """Return a list of persona names (filenames without .json extension).

    Scans the PERSONAS_DIR directory for *.json files.

    Returns:
        Sorted list of persona name strings. Returns an empty list if the
        directory does not exist.
    """
    if not PERSONAS_DIR.exists():
        return []

    return sorted(p.stem for p in PERSONAS_DIR.glob("*.json"))


def create_template(name: str) -> Path:
    """Create a new persona file pre-populated with placeholder values.

    Args:
        name: Persona name (without .json extension).

    Returns:
        Path of the newly created file.

    Raises:
        FileExistsError: If a persona file with that name already exists.
    """
    PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
    persona_path = PERSONAS_DIR / f"{name}.json"

    if persona_path.exists():
        raise FileExistsError(
            f"Persona file already exists: {persona_path}. "
            "Delete it first or choose a different name."
        )

    persona_path.write_text(
        json.dumps(TEMPLATE, indent=4),
        encoding="utf-8",
    )
    return persona_path
