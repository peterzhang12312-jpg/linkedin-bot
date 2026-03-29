"""
LinkedIn profile scraper using Playwright sync API.

Data flow:
  URL → page.goto(profile) → scrape profile dict
      → page.goto(recent-activity) → scrape posts list
      → return ProfileData

Error handling:
  - CAPTCHA/checkpoint → raise LinkedInCaptchaError
  - Login redirect → raise LinkedInSessionExpiredError
  - DOM selector miss → raise LinkedInDOMChangedError (with recovery hint)
  - Compose window timeout → raise ComposeWindowError (with clipboard fallback hint)
"""

import random
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LinkedInBotError(Exception):
    pass


class LinkedInCaptchaError(LinkedInBotError):
    """Raised when /checkpoint/ or /challenge/ is detected in the current URL."""
    pass


class LinkedInSessionExpiredError(LinkedInBotError):
    """Raised when the browser is redirected to /login or /authwall."""
    pass


class LinkedInDOMChangedError(LinkedInBotError):
    """Raised when a critical CSS/DOM selector returns None or raises AttributeError."""
    pass


class ComposeWindowError(LinkedInBotError):
    """Raised when the compose modal did not load within the expected timeout.

    Clipboard fallback hint: copy message text to clipboard with pyperclip before
    calling open_dm_compose() so the user can paste manually if this error fires.
    """
    pass


class LinkedInNotConnectedError(LinkedInBotError):
    """Raised when a Connect button is found instead of a Message button."""
    pass


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class LinkedInScraper:
    """Playwright-backed LinkedIn scraper using a persistent browser profile."""

    _input_fn = staticmethod(input)  # overridable in tests without patching builtins

    def __init__(self, profile_dir: str, headless: bool = False):
        """
        Initialize with a persistent browser profile directory.

        Args:
            profile_dir: Path to the Chromium user-data directory.  The directory
                         will be created on first launch and cookies/session data
                         are preserved between runs.
            headless:    Run the browser in headless mode.  Defaults to False so
                         that LinkedIn's bot-detection heuristics are easier to
                         satisfy with a visible browser.
        """
        self.profile_dir = profile_dir
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._page = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self):
        """Start Playwright and launch browser with persistent context."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            ignore_default_args=["--enable-automation"],
        )
        # Use the first page that the persistent context opens, or create one.
        if self._browser.pages:
            self._page = self._browser.pages[0]
        else:
            self._page = self._browser.new_page()
        return self

    def __exit__(self, *args):
        """Close browser and Playwright."""
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._playwright:
                self._playwright.stop()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_profile(self, url: str) -> dict:
        """
        Scrape a LinkedIn profile page.

        Returns dict with keys:
            name, headline, location, bio, experience (list), skills (list)

        Raises:
            LinkedInCaptchaError: if /checkpoint/ or /challenge/ detected
            LinkedInSessionExpiredError: if /login or /authwall detected
            LinkedInDOMChangedError: if critical selectors return None
        """
        page = self._page
        page.goto(url, wait_until="domcontentloaded")
        self._check_for_captcha_or_redirect(page)
        self._add_mouse_jitter(page)
        self._random_delay(2.0, 8.0)

        data = {
            "name": "",
            "headline": "",
            "location": "",
            "bio": "",
            "experience": [],
            "skills": [],
        }

        # --- name (h1 is the most stable anchor on profile pages) ---
        try:
            h1 = page.query_selector("h1")
            if h1 is None:
                raise LinkedInDOMChangedError(
                    "LinkedIn DOM may have changed — the name selector failed. "
                    "The scraper needs updating."
                )
            data["name"] = (h1.inner_text() or "").strip()
        except LinkedInDOMChangedError:
            raise
        except Exception:
            raise LinkedInDOMChangedError(
                "LinkedIn DOM may have changed — the name selector failed. "
                "The scraper needs updating."
            )

        # --- headline ---
        try:
            headline_el = page.query_selector("div.text-body-medium")
            if headline_el is None:
                # Fallback: element with data-generated-suggestion-target
                headline_el = page.query_selector("[data-generated-suggestion-target]")
            data["headline"] = (headline_el.inner_text() if headline_el else "").strip()
        except Exception:
            raise LinkedInDOMChangedError(
                "LinkedIn DOM may have changed — the headline selector failed. "
                "The scraper needs updating."
            )

        # --- location ---
        try:
            # Location typically lives in a span inside the top card section
            loc_el = page.query_selector("span.text-body-small.inline.t-black--light.break-words")
            if loc_el is None:
                # Broader fallback: any element whose text contains a comma (city, state pattern)
                loc_candidates = page.query_selector_all("span.text-body-small")
                for candidate in loc_candidates:
                    text = (candidate.inner_text() or "").strip()
                    if "," in text and len(text) < 80:
                        data["location"] = text
                        break
            else:
                data["location"] = (loc_el.inner_text() or "").strip()
        except Exception:
            # Location is non-critical; degrade gracefully
            data["location"] = ""

        # --- bio / about section ---
        try:
            # The About section is a <section> that contains an element with
            # visible text "About".  The actual bio lives in a div inside it.
            about_section = None
            sections = page.query_selector_all("section")
            for section in sections:
                try:
                    heading = section.query_selector("div#about, span#about, h2")
                    if heading and "about" in (heading.inner_text() or "").lower():
                        about_section = section
                        break
                    # Also check aria-label on the section itself
                    label = section.get_attribute("aria-label") or ""
                    if "about" in label.lower():
                        about_section = section
                        break
                except Exception:
                    continue

            if about_section:
                # Try the full-text span that LinkedIn renders
                bio_el = about_section.query_selector(
                    "div.display-flex.ph5.pv3 span[aria-hidden='true']"
                )
                if bio_el is None:
                    bio_el = about_section.query_selector("span[aria-hidden='true']")
                if bio_el is None:
                    bio_el = about_section.query_selector("p, div.pv-shared-text-with-see-more")
                data["bio"] = (bio_el.inner_text() if bio_el else "").strip()
        except Exception:
            # Bio is non-critical; degrade gracefully
            data["bio"] = ""

        # --- experience ---
        try:
            exp_section = None
            sections = page.query_selector_all("section")
            for section in sections:
                try:
                    label = section.get_attribute("aria-label") or ""
                    if "experience" in label.lower():
                        exp_section = section
                        break
                    heading = section.query_selector("div#experience, span#experience, h2")
                    if heading and "experience" in (heading.inner_text() or "").lower():
                        exp_section = section
                        break
                except Exception:
                    continue

            if exp_section:
                entries = exp_section.query_selector_all("li")
                for entry in entries:
                    try:
                        text = (entry.inner_text() or "").strip()
                        if text:
                            data["experience"].append(text)
                    except Exception:
                        continue
        except Exception:
            data["experience"] = []

        # --- skills ---
        try:
            skills_section = None
            sections = page.query_selector_all("section")
            for section in sections:
                try:
                    label = section.get_attribute("aria-label") or ""
                    if "skills" in label.lower():
                        skills_section = section
                        break
                except Exception:
                    continue

            if skills_section:
                skill_els = skills_section.query_selector_all("span[aria-hidden='true']")
                for el in skill_els:
                    try:
                        text = (el.inner_text() or "").strip()
                        if text and len(text) < 60:
                            data["skills"].append(text)
                    except Exception:
                        continue
        except Exception:
            data["skills"] = []

        return data

    def scrape_recent_posts(self, profile_url: str) -> list:
        """
        Navigate to <profile_url>/recent-activity/all/ and scrape up to 5 post texts.

        Returns list of post text strings (may be empty if no posts visible).
        Does NOT raise if posts are empty — caller handles graceful degrade.

        Raises:
            LinkedInCaptchaError: if /checkpoint/ or /challenge/ detected
            LinkedInSessionExpiredError: if redirect detected
        """
        page = self._page
        activity_url = profile_url.rstrip("/") + "/recent-activity/all/"
        page.goto(activity_url, wait_until="domcontentloaded")
        self._check_for_captcha_or_redirect(page)
        self._add_mouse_jitter(page)
        self._random_delay(2.0, 8.0)

        posts = []
        try:
            # Primary selector: feed items with a data-urn attribute
            post_els = page.query_selector_all("div[data-urn]")
            if not post_els:
                # Fallback to the legacy class name
                post_els = page.query_selector_all(".feed-shared-update-v2")

            for el in post_els[:5]:
                try:
                    # Prefer the aria-hidden span that holds the full post text
                    text_el = el.query_selector("span[aria-hidden='true']")
                    if text_el is None:
                        text_el = el.query_selector(".feed-shared-text span")
                    if text_el is None:
                        text_el = el
                    text = (text_el.inner_text() or "").strip()
                    if text:
                        posts.append(text)
                except Exception:
                    continue
        except Exception:
            # Degrade gracefully — empty posts is acceptable
            pass

        return posts

    def open_dm_compose(self, profile_url: str) -> None:
        """
        Navigate to profile and click the Message button to open compose modal.

        Raises:
            ComposeWindowError: if Message button not found within 10s
            LinkedInNotConnectedError: if Connect button found instead (not yet connected)
        """
        page = self._page
        page.goto(profile_url, wait_until="domcontentloaded")
        self._check_for_captcha_or_redirect(page)
        self._add_mouse_jitter(page)
        self._random_delay(2.0, 5.0)

        # Try to locate the Message button (case-insensitive)
        message_btn = None
        connect_btn = None
        deadline = time.time() + 10

        while time.time() < deadline:
            try:
                # XPath-based text match is more resilient than class names
                message_btn = page.query_selector(
                    "button:has-text('Message'), a:has-text('Message')"
                )
                if message_btn:
                    break
                connect_btn = page.query_selector(
                    "button:has-text('Connect'), a:has-text('Connect')"
                )
                if connect_btn:
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if message_btn:
            try:
                self._random_delay(0.5, 2.0)
                message_btn.click()
                # Wait briefly for the compose modal to appear
                page.wait_for_selector(
                    ".msg-form, .msg-overlay-conversation-bubble, [role='dialog']",
                    timeout=8000,
                )
            except PlaywrightTimeout:
                raise ComposeWindowError(
                    "Compose modal did not appear after clicking Message button. "
                    "(Clipboard fallback: use pyperclip.copy() before calling this method.)"
                )
            return

        if connect_btn:
            raise LinkedInNotConnectedError(
                "Not yet connected to this person — send a connection request first."
            )

        raise ComposeWindowError(
            "Could not find Message or Connect button. "
            "(Clipboard fallback: use pyperclip.copy() before calling this method.)"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_for_captcha_or_redirect(self, page) -> None:
        """Check current URL for CAPTCHA or login redirect.

        On CAPTCHA: pauses and prompts the user to solve it in the visible
        browser window, then re-checks once.  Raises LinkedInCaptchaError
        only if the CAPTCHA persists after the retry.
        """
        url = page.url
        if "/checkpoint/" in url or "/challenge/" in url:
            self._input_fn(
                "LinkedIn CAPTCHA detected — solve it in the browser window, "
                "then press Enter to retry..."
            )
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass  # best-effort wait; re-check URL regardless
            url = page.url  # re-read after user intervention
            if "/checkpoint/" in url or "/challenge/" in url:
                raise LinkedInCaptchaError(
                    f"CAPTCHA still present after retry. URL: {url}"
                )
            return  # CAPTCHA cleared — continue normally
        if "/login" in url or "/authwall" in url or "/uas/login" in url:
            raise LinkedInSessionExpiredError(
                f"LinkedIn session expired — browser was redirected to login. URL: {url}"
            )

    def _add_mouse_jitter(self, page) -> None:
        """Add 2-4 random mouse moves within ±20px of viewport center."""
        viewport = page.viewport_size or {"width": 1280, "height": 800}
        cx = viewport["width"] // 2
        cy = viewport["height"] // 2
        moves = random.randint(2, 4)
        for _ in range(moves):
            x = cx + random.randint(-20, 20)
            y = cy + random.randint(-20, 20)
            try:
                page.mouse.move(x, y)
            except Exception:
                pass
            time.sleep(random.uniform(0.1, 0.3))

    def _random_delay(self, min_s: float = 2.0, max_s: float = 8.0) -> None:
        """Sleep for a random duration between min_s and max_s seconds."""
        time.sleep(random.uniform(min_s, max_s))
