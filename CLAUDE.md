# LinkedIn High-Signal Networking Bot

## Project Overview
A privacy-first, human-in-the-loop LinkedIn networking bot. Scrapes profile data, generates personalized message drafts using Gemini AI, and opens the LinkedIn compose window for human review before sending.

## Key Architecture Decisions
- Python playwright (sync API) for browser automation — NOT gstack /browse (Node.js)
- Typer CLI framework
- google-genai SDK (same as attorney-matchmaker backend)
- Append-only JSONL for draft history
- External prompt template at prompts/generate_angles.txt

## Module Responsibilities
- `linkedin_bot/scraper.py` — Playwright profile + post scraper; CAPTCHA detection; DOM-change error handling
- `linkedin_bot/context.py` — ContextEngine: merges profile dict + posts list + persona JSON → context dict
- `linkedin_bot/generator.py` — Gemini API calls + Regen Policy (3 attempts/angle, 9 max total)
- `linkedin_bot/scanner.py` — AI-speak blocklist (deterministic keyword check)
- `linkedin_bot/history.py` — Append-only JSONL draft history at drafts/history.jsonl
- `linkedin_bot/personas.py` — Persona JSON loader with fail-fast validation
- `cli.py` — Typer CLI entry point

## Critical Rules
- NEVER use async playwright — sync API only
- NEVER hardcode personal info — use {{USER_BIO}} template variables in persona JSONs
- NEVER open LinkedIn compose window in --dry-run mode
- NEVER log history in --no-history mode
- ALWAYS wrap page.query_selector() in try/except for DOM-change resilience
- ALWAYS check for /checkpoint/ or /challenge/ in URL after page.goto() (CAPTCHA detection)
- Regen counter is PER ANGLE (3 max each), shared between AI-speak and 280-char failures

## Running
```bash
cd linkedin-bot
pip install -r requirements.txt
playwright install chromium
python -m playwright codegen  # to set up your profile
python cli.py run --url https://www.linkedin.com/in/someone --persona default
```

## Testing
```bash
cd linkedin-bot
pytest tests/ -v
```
