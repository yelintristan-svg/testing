# Websites

One group site and three sector sites, generated from a single config. Plain static HTML, CSS and JS, so it can be hosted anywhere (Netlify, Cloudflare Pages, Vercel, GitHub Pages, any web host).

| Site | Folder after build | Placeholder domain |
|---|---|---|
| Meridian Talent Group (corporate) | `dist/group/` | meridiantalent.co.uk |
| Meridian Care (nursing, medical & care) | `dist/care/` | meridiancare.co.uk |
| Meridian Build (engineering, construction & trades) | `dist/build/` | meridianbuild.co.uk |
| Meridian Finance (accounting & finance) | `dist/finance/` | meridianfinance.co.uk |

## Build

```bash
node build.js           # production: cross-site links use the domains in config.js
node build.js --local   # preview: relative links, open dist/index.html in a browser
```

Needs only Node 18+. No npm install.

## What to swap (all in `config.js`, marked `← SWAP`)

- Brand names, domains, emails, phone numbers
- Calendly links (one per site, can be the same link)
- `formEndpoint`: where all forms POST (Formspree to start, the CRM intake endpoint later)
- Your full name, LinkedIn, company social links, company number and address

## What each sector site has

- **Client / candidate toggle** on the home page. It swaps the hero, benefits, process, FAQs, CTAs, blog filter and the sticky join bar. Link straight to a view with `?for=candidate` or `?for=client` (useful in outreach emails). The visitor's last choice is remembered.
- `hire.html`: vacancy form plus inline Calendly booking (client landing page for outreach).
- `register.html`: candidate registration with LinkedIn URL and CV upload.
- **Blog** with an audience filter, a booking or register prompt mid-article, a job-alert/newsletter signup at the end, and a sticky "join" bar that appears after scrolling.
- Perm vs temp model per sector, explained on each site and on the group site:
  - Care: temp and locum first, permanent alongside
  - Build: contract and temp for site, permanent for engineers
  - Finance: permanent first, interim when needed

## Hooks for the CRM and automation

- Every form sends hidden `site` and `form` fields, plus page, referrer and any `utm_*` / `ref` params from the URL, so the CRM can attribute each lead to an outreach campaign.
- Calendly links get `utm_source=website&utm_medium=<site>&utm_content=<button>` so bookings show which page and button they came from.
- **Blog posts are Markdown files** in `content/blog/<site>/`. An AI agent (or a GitHub Action) can publish by adding a `.md` file and rebuilding. Frontmatter:

```
---
title: Post title
date: 2026-10-16
audience: client | candidate | both
excerpt: One or two sentences for cards and SEO.
author: optional, defaults to the owner name
---
Markdown body: ## headings, - lists, 1. lists, > quotes, **bold**, *italic*, [links](url)
```

- Each site gets `sitemap.xml`, `robots.txt`, canonical and Open Graph tags, and schema.org `EmploymentAgency` / `BlogPosting` data for SEO.

## Before going live

- Replace the placeholder privacy policy with one reviewed for UK GDPR.
- No testimonials, placement numbers or team members are shown, because none were real yet. Add them once they are.
