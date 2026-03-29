"""
Message generator using Gemini API.

Regen Policy (authoritative):
  - Each of the 3 angles has its own independent regen counter (max 3 attempts)
  - Counter increments on ANY failure: AI-speak OR over 280 chars
  - Total max API calls per target: 9 (3 angles × 3 attempts)
  - On counter exhaustion: present best attempt with [WARNING: quality check failed] flag
  - On Gemini API error: mark angle as [ERROR: generation failed], continue to next angle

Data flow:
  context dict → render_prompt(template, context) → Gemini API → parse JSON
               → for each angle: scan() + len() check → pass or regen
               → return list[DraftAngle]
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from google import genai

from linkedin_bot.scanner import scan
from linkedin_bot.context import render_prompt


@dataclass
class DraftAngle:
    hook: str           # "recent_post", "career_transition", etc.
    message: str        # The actual message text
    char_count: int     # len(message)
    warnings: list[str] = field(default_factory=list)  # ["quality check failed"] or ["generation failed"]
    attempts: int = 1   # how many regen attempts were needed


class MessageGenerator:
    MAX_CHARS = 280
    MAX_ATTEMPTS = 3

    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize Gemini client.
        api_key defaults to os.environ["GEMINI_API_KEY"]
        model defaults to os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        """
        resolved_key = api_key or os.environ["GEMINI_API_KEY"]
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self.client = genai.Client(api_key=resolved_key)

    def generate(self, context: dict) -> list[DraftAngle]:
        """
        Generate 3 message angles for the given context.

        Returns list of 3 DraftAngle objects (always exactly 3, even if some have warnings).
        Never raises — errors are captured in DraftAngle.warnings.
        """
        template = self._load_prompt_template()
        base_prompt = render_prompt(template, context)

        # Step 1: Get initial batch of all 3 angles from a single API call.
        try:
            all_angles = self._call_gemini(base_prompt)
        except Exception:
            # If the initial call itself fails, return 3 error angles immediately.
            return [
                DraftAngle(
                    hook="error",
                    message="[ERROR: generation failed]",
                    char_count=0,
                    warnings=["generation failed"],
                    attempts=1,
                )
                for _ in range(3)
            ]

        # Pad to 3 entries in case the model returned fewer than expected.
        while len(all_angles) < 3:
            all_angles.append({"hook": "error", "message": ""})

        results: list[DraftAngle] = []

        for i in range(3):
            raw = all_angles[i]
            hook = raw.get("hook", "unknown")
            message = raw.get("message", "")

            passes, issues = self._check_quality(message)

            if passes:
                results.append(
                    DraftAngle(
                        hook=hook,
                        message=message,
                        char_count=len(message),
                        warnings=[],
                        attempts=1,
                    )
                )
                continue

            # Regen loop — we've already consumed attempt 1 above.
            best_attempt = (message, hook, issues)
            attempt_number = 1

            while attempt_number < self.MAX_ATTEMPTS:
                attempt_number += 1
                regen_prompt = (
                    base_prompt
                    + f"\n\nThe previous angle {i + 1} was rejected due to: {', '.join(issues)}."
                    f" Generate a new version of angle {i + 1} only, keeping the other angles the same."
                )
                try:
                    regen_angles = self._call_gemini(regen_prompt)
                except Exception:
                    # API error during regen — record error angle immediately.
                    results.append(
                        DraftAngle(
                            hook="error",
                            message="[ERROR: generation failed]",
                            char_count=0,
                            warnings=["generation failed"],
                            attempts=attempt_number,
                        )
                    )
                    break

                # Extract the regenerated angle at position i.
                if i < len(regen_angles):
                    new_raw = regen_angles[i]
                else:
                    new_raw = {"hook": "unknown", "message": ""}

                new_hook = new_raw.get("hook", "unknown")
                new_message = new_raw.get("message", "")
                new_passes, new_issues = self._check_quality(new_message)

                if new_passes:
                    results.append(
                        DraftAngle(
                            hook=new_hook,
                            message=new_message,
                            char_count=len(new_message),
                            warnings=[],
                            attempts=attempt_number,
                        )
                    )
                    break  # Success — exit regen loop.

                # Not clean — track as best attempt (prefer any attempt over empty).
                best_attempt = (new_message, new_hook, new_issues)
            else:
                # Exhausted MAX_ATTEMPTS without a clean result — append warning angle.
                # (The while loop fell through without a break.)
                best_message, best_hook, _ = best_attempt
                results.append(
                    DraftAngle(
                        hook=best_hook,
                        message=best_message,
                        char_count=len(best_message),
                        warnings=["quality check failed"],
                        attempts=attempt_number,
                    )
                )

        return results

    def _call_gemini(self, prompt: str) -> list[dict]:
        """
        Call Gemini API and parse the JSON response.
        Returns list of angle dicts: [{"hook": "...", "message": "..."}, ...]
        Raises ValueError if response is not valid JSON or missing expected keys.
        Raises google.genai.errors.* on API errors.
        """
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        raw_text = response.text

        # Strip markdown code fences if the model wraps the JSON in ```json ... ```.
        stripped = raw_text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            # Drop first line (```json or ```) and last line (```)
            stripped = "\n".join(lines[1:-1]).strip()

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Gemini response is not valid JSON: {exc}") from exc

        if "angles" not in parsed:
            raise ValueError("Gemini response missing 'angles' key")

        angles = parsed["angles"]
        if not isinstance(angles, list):
            raise ValueError("'angles' must be a list")

        for entry in angles:
            if not isinstance(entry, dict):
                raise ValueError("Each angle must be a dict")
            if "hook" not in entry or "message" not in entry:
                raise ValueError("Each angle dict must have 'hook' and 'message' keys")

        return angles

    def _load_prompt_template(self) -> str:
        """Load prompts/generate_angles.txt. Raises FileNotFoundError if missing."""
        # Path is relative to this file's location: linkedin_bot/ -> ../prompts/
        prompts_path = Path(__file__).parent.parent / "prompts" / "generate_angles.txt"
        return prompts_path.read_text(encoding="utf-8")

    def _check_quality(self, message: str) -> tuple[bool, list[str]]:
        """
        Run quality checks on a single message.
        Returns (passes_all_checks, list_of_issues).
        Issues: "exceeds 280 chars ({n} chars)" or "AI-speak detected: {phrases}"
        """
        issues: list[str] = []

        char_count = len(message)
        if char_count > self.MAX_CHARS:
            issues.append(f"exceeds 280 chars ({char_count} chars)")

        is_clean, matched_phrases = scan(message)
        if not is_clean:
            issues.append(f"AI-speak detected: {matched_phrases}")

        passes = len(issues) == 0
        return passes, issues

    def _generate_angle(self, context: dict, angle_index: int) -> DraftAngle:
        """
        Generate a single angle with regen loop.
        angle_index: 0, 1, or 2 — used to request a specific angle from Gemini.
        """
        template = self._load_prompt_template()
        base_prompt = render_prompt(template, context)

        best_message = ""
        best_hook = "unknown"
        attempt_number = 0

        while attempt_number < self.MAX_ATTEMPTS:
            attempt_number += 1

            if attempt_number == 1:
                prompt = base_prompt
            else:
                prompt = (
                    base_prompt
                    + f"\n\nRegenerate angle {angle_index + 1} only."
                )

            try:
                angles = self._call_gemini(prompt)
            except Exception:
                return DraftAngle(
                    hook="error",
                    message="[ERROR: generation failed]",
                    char_count=0,
                    warnings=["generation failed"],
                    attempts=attempt_number,
                )

            if angle_index < len(angles):
                raw = angles[angle_index]
                hook = raw.get("hook", "unknown")
                message = raw.get("message", "")
            else:
                hook = "unknown"
                message = ""

            passes, issues = self._check_quality(message)

            if passes:
                return DraftAngle(
                    hook=hook,
                    message=message,
                    char_count=len(message),
                    warnings=[],
                    attempts=attempt_number,
                )

            best_message = message
            best_hook = hook

        # Exhausted all attempts.
        return DraftAngle(
            hook=best_hook,
            message=best_message,
            char_count=len(best_message),
            warnings=["quality check failed"],
            attempts=attempt_number,
        )
