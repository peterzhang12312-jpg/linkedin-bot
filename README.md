# LinkedIn Bot

> AI-generated outreach drafts. Human sends. Always.

Scrapes a LinkedIn profile + recent posts, generates 3 personalized connection messages under 280 characters using Gemini AI, opens the compose window — **you paste and click Send.**

No auto-sending. No risk. Just better first messages, faster.

---

## How It Works

```
python cli.py run --url https://www.linkedin.com/in/someone
```

```
Scraping profile...  ✓
Scraping recent posts...  ✓ (3 posts found)

Draft 1 (recent_post angle):
"Your post on agentic AI architectures resonated — the latency tradeoff point is
underrated. I'm building similar pipelines on the legal side. Would love to connect."

Draft 2 (career_transition angle):
"Congrats on the move to Anthropic — that's a big one. I'm working on Claude-powered
legal tools and would love to stay in your orbit. Connect?"

Draft 3 (shared_interest angle):
"Fellow believer that AI + domain expertise > pure AI. Building attorney-matching
on court records. Your work on eval frameworks is directly relevant. Connect?"

Pick a draft (1-3), r to regenerate, q to quit: 2
Opening LinkedIn compose window...
[browser opens, message pre-loaded]
Did you send it? (y/n): y
Saved to history.
```

---

## Install

```bash
git clone https://github.com/peterzhang12312-jpg/linkedin-bot.git
cd linkedin-bot
pip install -r requirements.txt
playwright install chromium
```

**Session setup (one-time):**

```bash
cp .env.example .env
# Add your GEMINI_API_KEY to .env
python cli.py setup-session
# Browser opens → log in to LinkedIn → press Enter
```

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com/).

---

## Usage

```bash
# Generate drafts for a profile
python cli.py run --url https://www.linkedin.com/in/someone

# Use a specific persona (founder, recruiter, etc.)
python cli.py run --url https://www.linkedin.com/in/someone --persona founder

# Dry run — drafts only, no browser
python cli.py run --url https://www.linkedin.com/in/someone --dry-run

# View send history
python cli.py history list

# List personas
python cli.py personas list
```

---

## Features

- **Playwright persistent session** — logs in once, reuses session. Handles CAPTCHA recovery.
- **Gemini 2.0 Flash** — fast, cheap, good. Generates 3 drafts per angle (recent post / career transition / shared interest).
- **AI-speak blocklist** — scans for "synergy", "game-changer", "excited to connect" and blocks them automatically.
- **280-char enforced** — LinkedIn connection limit. Every draft is guaranteed under it.
- **Multi-persona** — write as your "founder" self, your "recruiter" self, your "researcher" self.
- **Draft history** — append-only JSONL. Never lose a message you sent.
- **Human-in-the-loop** — bot never sends anything. You review, you send.

---

## Persona Setup

Edit `personas/default.json`:

```json
{
  "name": "Default",
  "USER_NAME": "Your Name",
  "USER_BIO": "Startup founder building AI tools for legal teams",
  "USER_GOAL": "Connect with ML engineers and AI researchers",
  "USER_TONE": "concise and direct",
  "preferred_angles": ["recent_post", "career_transition", "shared_interest"]
}
```

Create additional personas:

```bash
python cli.py personas new recruiter
```

---

## Stack

- **Python 3.11+** · **Playwright** (sync API) · **Gemini 2.0 Flash** · **Typer CLI**
- Append-only JSONL history · External prompt templates · 127 passing tests

---

## Troubleshooting

**CAPTCHA detected** — Solve it in the browser window, press Enter in the terminal.

**Session expired** — Run `python cli.py setup-session` and log in again.

**LinkedIn DOM changed** — Open an issue or update selectors in `linkedin_bot/scraper.py`.

---

## Contributing

PRs welcome. Run tests with:

```bash
pytest tests/ -v
```

---

*Built with [Claude Code](https://claude.ai/code)*
