"""
Tests for linkedin_bot.scraper using local HTML fixtures.

Playwright launches a real Chromium instance for DOM-interaction tests.
URL-based detection tests (CAPTCHA, session expired) mock page.url via
monkeypatching so they work without network access.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Playwright availability guard
# ---------------------------------------------------------------------------
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

requires_playwright = pytest.mark.skipif(
    not PLAYWRIGHT_AVAILABLE,
    reason="playwright not installed",
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def fixture_url(filename: str) -> str:
    """Return a file:// URL for a fixture HTML file (cross-platform)."""
    path = (FIXTURES_DIR / filename).resolve()
    # On Windows, Path.as_posix() gives C:/... which file:// needs as ///C:/...
    posix = path.as_posix()
    if not posix.startswith("/"):
        posix = "/" + posix
    return f"file://{posix}"


# ---------------------------------------------------------------------------
# Shared Playwright fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser_page():
    """Launch a non-persistent Chromium browser for the test session."""
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("playwright not installed")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


# ---------------------------------------------------------------------------
# Helpers: build a minimal LinkedInScraper-like object backed by a real page
# ---------------------------------------------------------------------------

def make_scraper_with_page(page):
    """
    Return a LinkedInScraper instance whose internal _page is already set to
    the supplied Playwright page.  We bypass __enter__ so no persistent profile
    directory is needed during tests.

    We also stub _check_for_captcha_or_redirect and _random_delay / _add_mouse_jitter
    to keep tests fast and URL-independent.
    """
    from linkedin_bot.scraper import LinkedInScraper

    scraper = object.__new__(LinkedInScraper)
    scraper.profile_dir = "/tmp/fake-profile"
    scraper.headless = True
    scraper._playwright = None
    scraper._browser = None
    scraper._page = page

    # Stub out side-effectful helpers for fast, deterministic tests
    scraper._check_for_captcha_or_redirect = lambda p: None
    scraper._add_mouse_jitter = lambda p: None
    scraper._random_delay = lambda *a, **kw: None

    return scraper


# ---------------------------------------------------------------------------
# Test 1 – scrape_profile extracts name correctly
# ---------------------------------------------------------------------------

@requires_playwright
def test_scrape_profile_name(browser_page):
    scraper = make_scraper_with_page(browser_page)
    result = scraper.scrape_profile(fixture_url("profile_full.html"))
    assert result["name"] == "Sarah Chen", (
        f"Expected 'Sarah Chen', got {result['name']!r}"
    )


# ---------------------------------------------------------------------------
# Test 2 – scrape_profile extracts headline correctly
# ---------------------------------------------------------------------------

@requires_playwright
def test_scrape_profile_headline(browser_page):
    scraper = make_scraper_with_page(browser_page)
    result = scraper.scrape_profile(fixture_url("profile_full.html"))
    assert result["headline"] == "Head of ML @ Stripe", (
        f"Expected 'Head of ML @ Stripe', got {result['headline']!r}"
    )


# ---------------------------------------------------------------------------
# Test 3 – missing bio returns empty string, not a crash
# ---------------------------------------------------------------------------

@requires_playwright
def test_scrape_profile_missing_bio_graceful(browser_page):
    """
    Inject minimal HTML with h1 but NO About section — bio should be empty string.
    Uses the shared browser_page fixture to avoid nesting sync_playwright() contexts.
    """
    minimal_html = """<!DOCTYPE html><html><body>
    <section><h1>Test User</h1>
    <div class="text-body-medium">Engineer</div></section>
    </body></html>"""

    browser_page.set_content(minimal_html)
    scraper = make_scraper_with_page(browser_page)
    # Override goto so it doesn't navigate away from our injected content
    scraper._page.goto = lambda url, **kw: None

    result = scraper.scrape_profile("file:///fake")
    assert result["bio"] == "", f"Expected empty bio, got {result['bio']!r}"


# ---------------------------------------------------------------------------
# Test 4 – scrape_recent_posts returns [] for no-posts fixture (no crash)
# ---------------------------------------------------------------------------

@requires_playwright
def test_scrape_recent_posts_empty(browser_page):
    scraper = make_scraper_with_page(browser_page)
    # Point recent-activity scraper at the no_posts fixture directly
    # by stubbing goto to load the fixture instead of the constructed URL
    original_goto = browser_page.goto

    def fake_goto(url, **kwargs):
        return original_goto(fixture_url("profile_no_posts.html"), **kwargs)

    browser_page.goto = fake_goto
    try:
        posts = scraper.scrape_recent_posts("https://www.linkedin.com/in/sarah-chen/")
        assert posts == [], f"Expected empty list, got {posts!r}"
    finally:
        browser_page.goto = original_goto


# ---------------------------------------------------------------------------
# Test 5 – LinkedInDOMChangedError raised when h1 is missing
# ---------------------------------------------------------------------------

@requires_playwright
def test_scrape_profile_raises_dom_changed_when_no_h1(browser_page):
    """
    Inject minimal HTML with no h1 — scraper must raise LinkedInDOMChangedError.
    Uses the shared browser_page fixture to avoid nesting sync_playwright() contexts.
    """
    from linkedin_bot.scraper import LinkedInDOMChangedError

    no_h1_html = """<!DOCTYPE html><html><body>
    <div>No heading here at all</div>
    </body></html>"""

    browser_page.set_content(no_h1_html)
    scraper = make_scraper_with_page(browser_page)
    scraper._page.goto = lambda url, **kw: None

    with pytest.raises(LinkedInDOMChangedError) as exc_info:
        scraper.scrape_profile("file:///fake")

    assert "name" in str(exc_info.value).lower(), (
        f"Error message should mention 'name': {exc_info.value}"
    )


# ---------------------------------------------------------------------------
# Test 6 – CAPTCHA detection via mocked page.url
# ---------------------------------------------------------------------------

def test_captcha_detection_raises_error():
    """
    _check_for_captcha_or_redirect raises LinkedInCaptchaError when
    /checkpoint/ persists after the user presses Enter.
    """
    from linkedin_bot.scraper import LinkedInScraper, LinkedInCaptchaError

    scraper = object.__new__(LinkedInScraper)
    scraper._input_fn = lambda prompt="": None  # skip the wait

    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/checkpoint/challenge/abc123"

    with pytest.raises(LinkedInCaptchaError):
        scraper._check_for_captcha_or_redirect(mock_page)


def test_challenge_url_raises_captcha_error():
    """URL containing /challenge/ should also trigger LinkedInCaptchaError."""
    from linkedin_bot.scraper import LinkedInScraper, LinkedInCaptchaError

    scraper = object.__new__(LinkedInScraper)
    scraper._input_fn = lambda prompt="": None

    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/challenge/solve?type=something"

    with pytest.raises(LinkedInCaptchaError):
        scraper._check_for_captcha_or_redirect(mock_page)


# ---------------------------------------------------------------------------
# Test 7 – Session expired detection via mocked page.url
# ---------------------------------------------------------------------------

def test_session_expired_login_redirect():
    """
    _check_for_captcha_or_redirect should raise LinkedInSessionExpiredError
    when the page URL contains /login.
    """
    from linkedin_bot.scraper import LinkedInScraper, LinkedInSessionExpiredError

    scraper = object.__new__(LinkedInScraper)
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/login?session_redirect=..."

    with pytest.raises(LinkedInSessionExpiredError):
        scraper._check_for_captcha_or_redirect(mock_page)


def test_session_expired_authwall_redirect():
    """/authwall should also raise LinkedInSessionExpiredError."""
    from linkedin_bot.scraper import LinkedInScraper, LinkedInSessionExpiredError

    scraper = object.__new__(LinkedInScraper)
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/authwall?trk=..."

    with pytest.raises(LinkedInSessionExpiredError):
        scraper._check_for_captcha_or_redirect(mock_page)


# ---------------------------------------------------------------------------
# Bonus: normal URL does not raise
# ---------------------------------------------------------------------------

def test_normal_url_does_not_raise():
    """A normal profile URL must not trigger any error."""
    from linkedin_bot.scraper import LinkedInScraper

    scraper = object.__new__(LinkedInScraper)
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/in/sarah-chen/"

    # Should complete without raising
    scraper._check_for_captcha_or_redirect(mock_page)


# ---------------------------------------------------------------------------
# CAPTCHA recovery — cleared on retry
# ---------------------------------------------------------------------------

def test_captcha_clears_after_user_resolves():
    """
    If the user solves the CAPTCHA before pressing Enter, page.url changes
    to a normal URL — no exception should be raised.
    """
    from linkedin_bot.scraper import LinkedInScraper

    scraper = object.__new__(LinkedInScraper)
    scraper._input_fn = lambda prompt="": None  # simulate instant Enter

    call_count = 0

    class FakePage:
        @property
        def url(self_inner):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "https://www.linkedin.com/checkpoint/challenge/abc123"
            return "https://www.linkedin.com/in/sarah-chen/"

        def wait_for_load_state(self_inner, *a, **kw):
            pass

    # Should not raise
    scraper._check_for_captcha_or_redirect(FakePage())


# ---------------------------------------------------------------------------
# CAPTCHA recovery — persists after retry
# ---------------------------------------------------------------------------

def test_captcha_persists_after_retry_raises_error():
    """
    If the CAPTCHA URL is still present after the user presses Enter,
    LinkedInCaptchaError must be raised.
    """
    from linkedin_bot.scraper import LinkedInScraper, LinkedInCaptchaError

    scraper = object.__new__(LinkedInScraper)
    scraper._input_fn = lambda prompt="": None

    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/checkpoint/challenge/abc123"
    mock_page.wait_for_load_state = MagicMock()

    with pytest.raises(LinkedInCaptchaError):
        scraper._check_for_captcha_or_redirect(mock_page)
