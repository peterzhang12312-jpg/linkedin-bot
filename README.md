# LinkedIn Bot

A personal LinkedIn networking tool. Scrapes a profile, generates 3 personalized
message drafts using AI, and opens the LinkedIn compose window — you paste and send.

**Human-in-the-loop:** the bot never sends anything automatically.

---

## Prerequisites

- Python 3.11 or newer — check with `python --version`
- Git — check with `git --version`
- A [Google AI Studio](https://aistudio.google.com/) account (free) for the Gemini API key
- A LinkedIn account

---

## Installation

```bash
git clone https://github.com/peterzhang12312-jpg/linkedin-bot.git
cd linkedin-bot
pip install -r requirements.txt
playwright install chromium
```

---

## LinkedIn Session Setup (one-time)

The bot uses a persistent browser profile so LinkedIn sees your real session.

**Step 1** — Create the profile directory:
```bash
mkdir li_profile
```

**Step 2** — Launch the browser and log in:
```bash
python -m playwright open --save-storage=li_profile/session.json linkedin.com
```

A browser window opens. Log in to LinkedIn normally. Once logged in, close the browser window. Your session is now saved in `li_profile/`.

**Step 3** — Set the profile path in `.env`:
```
LI_PROFILE_DIR=./li_profile
```

You won't need to log in again unless LinkedIn expires your session.

---

## API Key Setup

Copy the example file and fill it in:

```bash
# macOS / Linux
cp .env.example .env

# Windows
copy .env.example .env
```

Open `.env` and set:

```
GEMINI_API_KEY=your_key_here
LI_PROFILE_DIR=./li_profile
```

Get your Gemini API key free at [aistudio.google.com](https://aistudio.google.com/) →
click "Get API key".

---

## Persona Setup

A persona tells the bot who you are so it can write messages in your voice.

Open `personas/default.json` and replace the placeholder values:

```json
{
  "name": "Default",
  "USER_NAME": "YOUR_NAME_HERE",
  "USER_BIO": "YOUR_BIO_HERE — e.g. 'Startup founder building AI tools for legal teams'",
  "USER_GOAL": "YOUR_GOAL_HERE — e.g. 'Connect with ML engineers and AI researchers'",
  "USER_TONE": "concise and direct",
  "preferred_angles": ["recent_post", "career_transition", "shared_interest"]
}
```

You can create additional personas (e.g. `recruiter`, `investor`) with:

```bash
python cli.py personas new my-persona
```

---

## Usage

```bash
# Generate drafts for a LinkedIn profile
python cli.py run --url https://www.linkedin.com/in/someone

# Use a specific persona
python cli.py run --url https://www.linkedin.com/in/someone --persona founder

# Dry run — generate drafts without opening LinkedIn compose window
python cli.py run --url https://www.linkedin.com/in/someone --dry-run

# See what you have sent before
python cli.py history list

# List available personas
python cli.py personas list
```

---

## Workflow

1. Bot scrapes the profile and recent posts
2. Bot shows 3 draft messages (under 280 characters each)
3. You pick one (or ask for a regeneration)
4. Bot opens the LinkedIn compose window
5. You paste the message and click Send
6. CLI asks "Did you send it?" — updates your history

---

## Troubleshooting

**CAPTCHA detected**
LinkedIn showed a CAPTCHA. Solve it in the browser window that opened, then press Enter.

**Session expired — re-login required**
Your LinkedIn session expired. Run:
```bash
python -m playwright open --save-storage=li_profile/session.json linkedin.com
```
Log in again and close the browser.

**LinkedIn DOM changed — selectors need updating**
LinkedIn changed their HTML. Open an issue or update the selectors in
`linkedin_bot/scraper.py`.

**GEMINI_API_KEY not set**
Make sure you copied `.env.example` to `.env` and filled in your key.
