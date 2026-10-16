# AI-Assisted Recruitment Agency

Home for the recruitment agency project: one group brand, three specialist sector brands (care, engineering/construction, finance), one human recruiter (Tristan) and openly disclosed AI recruitment assistants that research, run outreach and book calls.

> **Snapshot notice:** the `blueprint/`, `websites/` and `crm/` folders are a snapshot of the project's shared files taken on 16 Oct 2026. Work on several of them was still in progress at the time, so expect gaps (for example the empty `crm/tests/`, `crm/sequences/` and blog folders) that later commits will fill in.

## The plan

The full plan lives in [`blueprint/business-blueprint.md`](blueprint/business-blueprint.md). In short:

1. **Brands.** Northbridge Talent Group (placeholder name) with Care, Engineering and Finance divisions, all built from one codebase and design system.
2. **Operating model.** Tristan handles calls, interviews, offers and relationships. AI assistants, labelled as AI on every site, handle research, CRM enrichment, personalised email sequences, reply handling and booking.
3. **Systems.** A CRM with a compliant outreach engine (UK GDPR / PECR: suppression lists, unsubscribe links, throttled sending, dry-run by default), static websites with blogs for inbound traffic, and a calendar booking flow.
4. **Phasing.** Perm first across all sectors, with temp/contract added later where it makes sense.

## Layout

| Folder | What it is |
|---|---|
| `blueprint/` | Business blueprint: brands, perm vs temp, operating model, system architecture, UK compliance, tech stack. |
| `websites/` | Zero-dependency static site builder for the group site and three sector sites. |
| `crm/` | Python CRM and outreach engine: importers, compliance checks, Claude-drafted personalisation, sequences, mailer, booking. |

The trading scripts at the repo root (`hl_*.py`, `hyperliquid_*.py`) and their workflows in `.github/workflows/` predate this project and are unrelated to it.

## Running things

**Websites** (needs Node.js):

```bash
cd websites
node build.js --local   # builds dist/ with relative links so you can open it in a browser
```

**CRM** (needs Python 3):

```bash
cd crm
pip install anthropic   # only needed for AI-drafted emails
export ANTHROPIC_API_KEY=...        # set in your shell or a local .env, never commit it
export CRM_UNSUB_SECRET=...
```

The mailer defaults to dry-run (writes `.eml` files to an outbox). Live SMTP sending is wired but stays off unless explicitly enabled. See `crm/crm/settings.py` for every setting and environment variable.

## Secrets

No credentials live in this repo. API keys, the SMTP password, the Calendly signing key and the unsubscribe secret are read from environment variables only. `.env` files are ignored by git.

## Opening this on another computer

```bash
git clone https://github.com/yelintristan-svg/testing.git
cd testing
```

Or open https://github.com/yelintristan-svg/testing in a browser and use **Code → Open with GitHub Desktop** or **Download ZIP**.
