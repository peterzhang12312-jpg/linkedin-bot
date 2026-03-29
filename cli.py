"""
LinkedIn networking bot CLI.

Usage:
    python cli.py run --url URL [--persona NAME] [--profile DIR] [--dry-run] [--no-history] [--verbose]
    python cli.py personas list
    python cli.py personas new NAME
    python cli.py history show --url URL [--limit N]
    python cli.py history list [--limit N]
    python cli.py setup-session [--profile DIR]
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

import sys
from datetime import datetime, timezone
from typing import Optional

import typer

from linkedin_bot import history as hist
from linkedin_bot import personas
from linkedin_bot.context import build_context
from linkedin_bot.generator import MessageGenerator, DraftAngle
from linkedin_bot.scraper import (
    LinkedInScraper,
    LinkedInCaptchaError,
    LinkedInSessionExpiredError,
    LinkedInDOMChangedError,
    LinkedInNotConnectedError,
    ComposeWindowError,
)

# ---------------------------------------------------------------------------
# Try to import rich for pretty separators; fall back to plain dashes
# ---------------------------------------------------------------------------
try:
    from rich.console import Console as _RichConsole
    _rich_console = _RichConsole()

    def _separator() -> str:
        return "\u2501" * 44  # rich heavy horizontal line

    HAVE_RICH = True
except ImportError:  # pragma: no cover
    HAVE_RICH = False

    def _separator() -> str:  # type: ignore[misc]
        return "-" * 44


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = typer.Typer(add_completion=False, no_args_is_help=True)
personas_app = typer.Typer(no_args_is_help=True)
history_app = typer.Typer(no_args_is_help=True)

app.add_typer(personas_app, name="personas")
app.add_typer(history_app, name="history")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _display_angles(angles: list[DraftAngle]) -> None:
    """Print the 3 draft angles with separators, char counts, and warnings."""
    for i, angle in enumerate(angles, start=1):
        sep = _separator()
        warnings_str = ""
        if angle.warnings:
            warnings_str = f" [WARNING: {'; '.join(angle.warnings)}]"
        header = f"DRAFT {i} \u2014 {angle.hook} ({angle.char_count} chars){warnings_str}"
        typer.echo(sep)
        typer.echo(header)
        typer.echo(sep)
        typer.echo(angle.message)
        typer.echo("")


def _prompt_angle_selection(angles: list[DraftAngle]) -> DraftAngle | None:
    """
    Prompt the user to select an angle (1/2/3) or 'r' to regenerate.
    Returns the selected DraftAngle, or None if user chose 'r'.
    Re-prompts on invalid input.
    """
    while True:
        choice = typer.prompt("Select angle (1/2/3, or 'r' to regenerate all)")
        choice = choice.strip().lower()
        if choice == "r":
            return None
        if choice in ("1", "2", "3"):
            return angles[int(choice) - 1]
        typer.echo("Invalid selection. Please enter 1, 2, 3, or 'r'.")


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------

@app.command()
def run(
    url: str = typer.Option(..., help="LinkedIn profile URL"),
    persona: str = typer.Option("default", "--persona", help="Persona name to use"),
    profile_dir: Optional[str] = typer.Option(None, "--profile", help="Playwright profile directory"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip opening compose window"),
    no_history: bool = typer.Option(False, "--no-history", help="Skip history read/write"),
    verbose: bool = typer.Option(False, "--verbose", help="Print scraped profile data"),
) -> None:
    """Run the full LinkedIn networking workflow."""

    # 1. Load persona
    try:
        persona_data = personas.load(persona)
    except personas.PersonaValidationError as exc:
        typer.echo(f"Persona validation error: {exc}")
        raise typer.Exit(1)
    except FileNotFoundError as exc:
        typer.echo(f"Persona not found: {exc}")
        raise typer.Exit(1)

    # 2. Show previous drafts if history enabled
    if not no_history:
        previous = hist.get_recent_for_url(url, limit=3)
        if previous:
            typer.echo("Previous drafts for this URL:")
            for entry in previous:
                typer.echo(f"  {hist.format_entry_summary(entry)}")
            typer.echo("")

    # 3. Scrape profile
    try:
        with LinkedInScraper(profile_dir=profile_dir) as scraper:
            profile_data = scraper.scrape_profile(url)
            posts = scraper.scrape_recent_posts(url)

            if verbose:
                typer.echo(f"Scraped profile: {profile_data}")
                typer.echo(f"Posts scraped: {len(posts)}")

            # 4. Build context
            context = build_context(profile_data, posts, persona_data)

            # 5. Warn if no posts
            if not posts:
                typer.echo("No recent posts found \u2014 using bio-only context.")

            # 6. Initialize generator (may raise KeyError for missing API key)
            try:
                generator = MessageGenerator()
            except KeyError:
                typer.echo("GEMINI_API_KEY not set. Add it to .env file.")
                raise typer.Exit(1)

            # 7. Generate angles (max 2 rounds)
            angles = generator.generate(context)
            _display_angles(angles)

            all_failed = all("generation failed" in a.warnings for a in angles)
            if all_failed:
                typer.echo("All angles failed to generate.")
                raise typer.Exit(1)

            # 8. Angle selection loop (max 2 generation rounds)
            selected: DraftAngle | None = None
            generation_round = 1

            while selected is None:
                selected = _prompt_angle_selection(angles)
                if selected is None:
                    if generation_round >= 2:
                        # Already regenerated once — force selection
                        typer.echo("Maximum regeneration rounds reached. Please select an angle.")
                        while selected is None:
                            selected = _prompt_angle_selection(angles)
                            if selected is None:
                                typer.echo("Please select 1, 2, or 3.")
                        break
                    generation_round += 1
                    typer.echo("Regenerating all angles...")
                    angles = generator.generate(context)
                    _display_angles(angles)
                    all_failed = all("generation failed" in a.warnings for a in angles)
                    if all_failed:
                        typer.echo("All angles failed to generate.")
                        raise typer.Exit(1)

            # 9. Copy to clipboard
            import pyperclip
            pyperclip.copy(selected.message)

            # 10. Open compose window unless dry-run
            if not dry_run:
                try:
                    scraper.open_dm_compose(url)
                except LinkedInNotConnectedError:
                    typer.echo("Not yet connected \u2014 send a connection request first.")
                    raise typer.Exit(1)
                except ComposeWindowError:
                    typer.echo("Could not open compose window \u2014 message copied to clipboard.")

            typer.echo("Message copied to clipboard. Paste it in LinkedIn and click Send.")

            # 11. Save history
            if not no_history:
                now_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                entry = hist.make_entry(
                    url=url,
                    persona=persona,
                    target_name=profile_data.get("name", ""),
                    target_role=profile_data.get("headline", ""),
                    angles=[a.message for a in angles],
                    chosen_index=None,
                    timestamp=now_ts,
                )
                hist.append_entry(entry)

                if not dry_run:
                    sent = typer.prompt("Did you send it? (y/N)", default="N")
                    if sent.strip().lower() == "y":
                        # Find the angle index in the current angles list
                        chosen_idx = next(
                            (i for i, a in enumerate(angles) if a.message == selected.message),
                            0,
                        )
                        hist.update_chosen_index(url, now_ts, chosen_idx)

    except LinkedInCaptchaError as exc:
        typer.echo(f"CAPTCHA detected \u2014 please solve it manually and retry. ({exc})")
        raise typer.Exit(1)
    except LinkedInSessionExpiredError as exc:
        typer.echo(f"LinkedIn session expired \u2014 re-login required. ({exc})")
        raise typer.Exit(1)
    except LinkedInDOMChangedError as exc:
        typer.echo(f"LinkedIn DOM changed \u2014 selectors need updating. ({exc})")
        raise typer.Exit(1)
    except typer.Exit:
        raise


# ---------------------------------------------------------------------------
# personas subcommands
# ---------------------------------------------------------------------------

@personas_app.command("list")
def personas_list() -> None:
    """List all available personas."""
    names = personas.list_personas()
    if not names:
        typer.echo("No personas found. Create one with: python cli.py personas new NAME")
        return
    typer.echo("Available personas:")
    for i, name in enumerate(names, start=1):
        typer.echo(f"  {i}. {name}")


@personas_app.command("new")
def personas_new(name: str = typer.Argument(..., help="Persona name (without .json)")) -> None:
    """Create a new persona template file."""
    try:
        path = personas.create_template(name)
        typer.echo(f"Created persona template: {path}")
    except FileExistsError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# history subcommands
# ---------------------------------------------------------------------------

@history_app.command("show")
def history_show(
    url: str = typer.Option(..., help="LinkedIn profile URL"),
    limit: int = typer.Option(10, "--limit", help="Number of entries to show"),
) -> None:
    """Show draft history for a specific URL."""
    entries = hist.get_recent_for_url(url, limit=limit)
    if not entries:
        typer.echo("No history for this URL.")
        return
    for entry in entries:
        typer.echo(hist.format_entry_summary(entry))


@history_app.command("list")
def history_list(
    limit: int = typer.Option(20, "--limit", help="Number of recent entries to show"),
) -> None:
    """Show recent drafts across all URLs."""
    entries = hist.list_recent(limit=limit)
    if not entries:
        typer.echo("No history found.")
        return
    for entry in entries:
        typer.echo(hist.format_entry_summary(entry))


# ---------------------------------------------------------------------------
# setup-session command
# ---------------------------------------------------------------------------

@app.command("setup-session")
def setup_session(
    profile_dir: Optional[str] = typer.Option(None, "--profile", help="Playwright profile directory"),
) -> None:
    """Open a browser to log in to LinkedIn and save the session."""
    import os
    from playwright.sync_api import sync_playwright

    # Resolve profile directory: CLI flag > env var > default
    resolved_dir = profile_dir or os.environ.get("LI_PROFILE_DIR") or "./li_profile"

    typer.echo(f"Opening browser with profile directory: {resolved_dir}")
    typer.echo("Log in to LinkedIn in the browser window, then come back here and press Enter.")

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=resolved_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            ignore_default_args=["--enable-automation"],
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        typer.prompt("Press Enter once you are logged in", default="", prompt_suffix="")
        browser.close()

    typer.echo(f"Session saved. You can now run: python cli.py run --url <linkedin_url>")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
