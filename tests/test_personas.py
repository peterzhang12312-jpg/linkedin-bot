"""Tests for linkedin_bot.personas module.

Uses tmp_path and monkeypatch to redirect PERSONAS_DIR so tests are fully
isolated from any real personas/ directory on disk.
"""

import json
import pytest

import linkedin_bot.personas as personas_module
from linkedin_bot.personas import (
    PersonaValidationError,
    create_template,
    list_personas,
    load,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_persona(directory, name: str, data: dict) -> None:
    """Write a persona JSON file into *directory*."""
    (directory / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


VALID_PERSONA = {
    "name": "Test Persona",
    "USER_NAME": "Jane Doe",
    "USER_BIO": "Engineer and builder. Two sentences right here.",
    "USER_GOAL": "Expand my professional network.",
    "USER_TONE": "warm and professional",
    "preferred_angles": ["recent_post", "shared_interest"],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def isolated_personas_dir(tmp_path, monkeypatch):
    """Redirect PERSONAS_DIR to a fresh tmp directory for each test."""
    fake_dir = tmp_path / "personas"
    fake_dir.mkdir()
    monkeypatch.setattr(personas_module, "PERSONAS_DIR", fake_dir)
    return fake_dir


# ---------------------------------------------------------------------------
# Test: load() — happy paths
# ---------------------------------------------------------------------------

def test_load_returns_correct_dict(isolated_personas_dir):
    """load() returns the full persona dict for a valid persona file."""
    _write_persona(isolated_personas_dir, "test", VALID_PERSONA)
    result = load("test")
    assert result == VALID_PERSONA


def test_load_succeeds_without_optional_preferred_angles(isolated_personas_dir):
    """load() does not require the optional preferred_angles field."""
    data = {k: v for k, v in VALID_PERSONA.items() if k != "preferred_angles"}
    _write_persona(isolated_personas_dir, "no_angles", data)
    result = load("no_angles")
    assert "USER_NAME" in result
    assert "preferred_angles" not in result


def test_load_succeeds_without_optional_name(isolated_personas_dir):
    """load() does not require the optional name field."""
    data = {k: v for k, v in VALID_PERSONA.items() if k != "name"}
    _write_persona(isolated_personas_dir, "no_name", data)
    result = load("no_name")
    assert result["USER_NAME"] == VALID_PERSONA["USER_NAME"]
    assert "name" not in result


# ---------------------------------------------------------------------------
# Test: load() — error paths
# ---------------------------------------------------------------------------

def test_load_raises_file_not_found_with_helpful_message(isolated_personas_dir):
    """load() raises FileNotFoundError with fix instructions for a missing file."""
    with pytest.raises(FileNotFoundError) as exc_info:
        load("nonexistent")
    assert "nonexistent" in str(exc_info.value)
    assert "python cli.py personas new nonexistent" in str(exc_info.value)


def test_load_raises_validation_error_for_missing_user_bio(isolated_personas_dir):
    """load() raises PersonaValidationError when USER_BIO is absent."""
    data = {k: v for k, v in VALID_PERSONA.items() if k != "USER_BIO"}
    _write_persona(isolated_personas_dir, "no_bio", data)
    with pytest.raises(PersonaValidationError) as exc_info:
        load("no_bio")
    assert "USER_BIO" in str(exc_info.value)


def test_load_raises_validation_error_for_missing_user_name(isolated_personas_dir):
    """load() raises PersonaValidationError when USER_NAME is absent."""
    data = {k: v for k, v in VALID_PERSONA.items() if k != "USER_NAME"}
    _write_persona(isolated_personas_dir, "no_username", data)
    with pytest.raises(PersonaValidationError) as exc_info:
        load("no_username")
    assert "USER_NAME" in str(exc_info.value)


def test_load_raises_validation_error_for_missing_user_goal(isolated_personas_dir):
    """load() raises PersonaValidationError when USER_GOAL is absent."""
    data = {k: v for k, v in VALID_PERSONA.items() if k != "USER_GOAL"}
    _write_persona(isolated_personas_dir, "no_goal", data)
    with pytest.raises(PersonaValidationError) as exc_info:
        load("no_goal")
    assert "USER_GOAL" in str(exc_info.value)


def test_load_raises_validation_error_for_missing_user_tone(isolated_personas_dir):
    """load() raises PersonaValidationError when USER_TONE is absent."""
    data = {k: v for k, v in VALID_PERSONA.items() if k != "USER_TONE"}
    _write_persona(isolated_personas_dir, "no_tone", data)
    with pytest.raises(PersonaValidationError) as exc_info:
        load("no_tone")
    assert "USER_TONE" in str(exc_info.value)


def test_load_raises_validation_error_for_invalid_json(isolated_personas_dir):
    """load() raises PersonaValidationError when the file contains invalid JSON."""
    bad_file = isolated_personas_dir / "broken.json"
    bad_file.write_text("{not valid json: !!!", encoding="utf-8")
    with pytest.raises(PersonaValidationError) as exc_info:
        load("broken")
    assert "invalid JSON" in str(exc_info.value)


def test_load_error_message_contains_field_name_and_fix_instruction(isolated_personas_dir):
    """Error message for a missing field includes both the field name and fix command."""
    data = {k: v for k, v in VALID_PERSONA.items() if k != "USER_BIO"}
    _write_persona(isolated_personas_dir, "founder", data)
    with pytest.raises(PersonaValidationError) as exc_info:
        load("founder")
    error_text = str(exc_info.value)
    assert "USER_BIO" in error_text
    assert "python cli.py personas new founder" in error_text


# ---------------------------------------------------------------------------
# Test: list_personas()
# ---------------------------------------------------------------------------

def test_list_personas_returns_correct_names(isolated_personas_dir):
    """list_personas() returns filenames without the .json extension."""
    for persona_name in ("alpha", "beta", "gamma"):
        _write_persona(isolated_personas_dir, persona_name, VALID_PERSONA)
    result = list_personas()
    assert sorted(result) == ["alpha", "beta", "gamma"]


def test_list_personas_returns_empty_list_when_directory_missing(monkeypatch, tmp_path):
    """list_personas() returns [] when PERSONAS_DIR does not exist."""
    missing_dir = tmp_path / "does_not_exist"
    monkeypatch.setattr(personas_module, "PERSONAS_DIR", missing_dir)
    result = list_personas()
    assert result == []


# ---------------------------------------------------------------------------
# Test: create_template()
# ---------------------------------------------------------------------------

def test_create_template_creates_file_with_correct_content(isolated_personas_dir):
    """create_template() writes a JSON file matching the TEMPLATE constant."""
    path = create_template("newpersona")
    assert path.exists()
    content = json.loads(path.read_text(encoding="utf-8"))
    assert content == personas_module.TEMPLATE


def test_create_template_raises_file_exists_error_if_already_exists(isolated_personas_dir):
    """create_template() raises FileExistsError when the persona file already exists."""
    _write_persona(isolated_personas_dir, "existing", VALID_PERSONA)
    with pytest.raises(FileExistsError):
        create_template("existing")
