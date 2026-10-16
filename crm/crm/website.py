"""A company's own website: find it, confirm it's theirs, read its team and contact pages.

Companies House doesn't record websites, so we try the obvious domains for
the company name (brookfoods.co.uk, brook-foods.com, ...) and only accept one
that names the company's registered number or registered postcode. UK
companies must show their registered number and office on their website, so
this rules out a namesake's site.

Only a handful of pages per site are read (home, about, team, people,
contact, legal), through `net.Polite`, which honours robots.txt and spaces
requests out. Nothing is stored except the names, job titles and work
addresses the company publishes about its own staff.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser

from . import net

NAME_SUFFIXES = {"limited", "ltd", "plc", "llp", "lp", "uk", "u.k.", "(uk)", "the", "co", "company"}
OPTIONAL_WORDS = {"group", "holdings", "services", "solutions", "international", "and"}
TLDS = ("co.uk", "com", "uk")
LINK_WORDS = ("team", "people", "about", "who-we-are", "leadership", "management", "board", "staff",
              "meet", "contact", "privacy", "legal", "terms")
VERIFY_FIRST = ("contact", "privacy", "legal", "terms", "about")
BLOCK_TAGS = {"p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6",
              "section", "article", "header", "footer", "figure", "figcaption", "dt", "dd", "button"}
EMAIL_RE = re.compile(r"[a-z0-9][a-z0-9._%+'-]*@[a-z0-9.-]+\.[a-z]{2,}", re.I)
POSTNOMINALS = {"aca", "fca", "acca", "fcca", "cima", "acma", "fcma", "cgma", "cta", "ata", "bsc", "ba", "ma",
                "msc", "mba", "bfp", "hons", "mcia", "cpa", "aat", "maat", "faat", "cfa", "ctp", "frsa", "obe", "mbe"}
HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "dame"}
NOT_NAMES = {"our", "the", "meet", "team", "contact", "us", "about", "read", "more", "view", "profile", "head",
             "office", "director", "manager", "finance", "financial", "services", "limited", "ltd", "group",
             "home", "news", "careers", "privacy", "policy", "and", "of", "for", "board", "senior", "leadership",
             "management", "people", "email", "phone", "call", "linkedin", "department", "accounts", "company"}
NAME_WORD = re.compile(r"^(?:[A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)*|Mc[A-Z][a-z]+|Mac[A-Z][a-z]+|O'[A-Z][a-z]+|[A-Z]\.?)$")


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.mailtos: list[str] = []
        self._buf: list[str] = []
        self._skip = 0
        self._href: str | None = None
        self._anchor: list[str] = []

    def _flush(self):
        line = " ".join("".join(self._buf).split())
        if line:
            self.lines.append(line)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self._skip += 1
        if tag in BLOCK_TAGS:
            self._flush()
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href.lower().startswith("mailto:"):
                self.mailtos.append(urllib.parse.unquote(href[7:].split("?")[0]))
            self._href, self._anchor = href, []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._anchor).split())))
            self._href = None
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self._skip:
            return
        self._buf.append(data)
        if self._href is not None:
            self._anchor.append(data)

    def close(self):
        super().close()
        self._flush()


@dataclass
class Page:
    url: str
    lines: list[str]
    links: list[tuple[str, str]]
    emails: set[str]


@dataclass
class Site:
    domain: str
    pages: list[Page] = field(default_factory=list)

    @property
    def emails(self) -> set[str]:
        return {e for p in self.pages for e in p.emails if e.endswith("@" + self.domain)
                or e.endswith("." + self.domain)}


def parse(url: str, html: str) -> Page:
    t = _Text()
    t.feed(html)
    t.close()
    text = unescape("\n".join(t.lines))
    # "name [at] domain [dot] co [dot] uk" style obfuscation is common on small firms' sites.
    deob = re.sub(r"\s*[\[\(]\s*at\s*[\]\)]\s*", "@", text, flags=re.I)
    deob = re.sub(r"\s*[\[\(]\s*dot\s*[\]\)]\s*", ".", deob, flags=re.I)
    emails = {e.lower().strip(".") for e in EMAIL_RE.findall(deob)} | {m.lower().strip() for m in t.mailtos if "@" in m}
    return Page(url, t.lines, t.links, emails)


def candidate_domains(company_name: str) -> list[str]:
    words = re.sub(r"[^a-z0-9& ]+", " ", company_name.lower().replace("&", " and ")).split()
    words = [w for w in words if w not in NAME_SUFFIXES]
    if not words:
        return []
    variants = [words]
    core = [w for w in words if w not in OPTIONAL_WORDS]
    if core and core != words:
        variants.append(core)
    out: list[str] = []
    for v in variants:
        for stem in ("".join(v), "-".join(v)):
            for tld in TLDS:
                d = f"{stem}.{tld}"
                if d not in out and len(stem) >= 3:
                    out.append(d)
    out.insert(2, "".join(words) + "ltd.co.uk")
    return out[:10]


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def mentions_company(page: Page, number: str, postcode: str) -> bool:
    text = _norm(" ".join(page.lines))
    num = _norm(number)
    if num and (num in text or (num.isdigit() and num.lstrip("0") and
                                re.search(r"(?<!\d)0*" + num.lstrip("0") + r"(?!\d)", " ".join(page.lines)))):
        return True
    pc = _norm(postcode)
    return len(pc) >= 5 and pc in text


def _internal_links(page: Page, domain: str) -> list[str]:
    seen, scored = set(), []
    for href, anchor in page.links:
        url = urllib.parse.urljoin(page.url, href.split("#")[0])
        if net.host_of(url) != domain or url in seen or url.rstrip("/") == page.url.rstrip("/"):
            continue
        if re.search(r"\.(pdf|jpe?g|png|gif|zip|docx?|xlsx?)$", url, re.I):
            continue
        seen.add(url)
        hay = (url + " " + anchor).lower()
        hits = [w for w in LINK_WORDS if w in hay]
        if hits:
            first = min(VERIFY_FIRST.index(w) for w in hits if w in VERIFY_FIRST) if any(
                w in VERIFY_FIRST for w in hits) else 9
            scored.append((first, url))
    return [u for _, u in sorted(scored)]


def find_site(polite: net.Polite, company_name: str, number: str, postcode: str, *,
              domains: list[str] | None = None, max_pages: int = 6) -> Site | None:
    """Try likely domains; keep the first whose pages name the company's number or postcode."""
    for d in domains or candidate_domains(company_name):
        got = polite.get(f"https://{d}/") or polite.get(f"https://www.{d}/")
        if not got or got[0] != 200 or not got[2]:
            continue
        home = parse(got[1], got[2])
        domain = net.host_of(got[1]) or d
        site = Site(domain, [home])
        verified = mentions_company(home, number, postcode)
        queue = _internal_links(home, domain)
        checked = 0
        while queue and len(site.pages) < max_pages:
            if not verified and checked >= 3:
                break
            url = queue.pop(0)
            r = polite.get(url)
            checked += 1
            if not r or r[0] != 200 or not r[2]:
                continue
            page = parse(r[1], r[2])
            site.pages.append(page)
            verified = verified or mentions_company(page, number, postcode)
        if verified:
            return site
    return None


# -- people on the page -------------------------------------------------------

def _title_hit(line: str, titles: list[str]) -> str:
    low = line.lower()
    best = ""
    for t in titles:
        if re.search(r"(?<![a-z])" + re.escape(t.lower()) + r"(?![a-z])", low) and len(t) > len(best):
            best = t
    return best


def clean_name(text: str) -> tuple[str, str] | None:
    words = [w.strip(",.") for w in text.replace(" ", " ").split()]
    words = [w for w in words if w and w.lower().strip(".") not in HONORIFICS]
    while words and (words[-1].lower().strip("()") in POSTNOMINALS or (words[-1].isupper() and len(words[-1]) <= 5
                                                                     and len(words) > 2)):
        words.pop()
    if not 2 <= len(words) <= 4:
        return None
    if any(w.lower() in NOT_NAMES or not NAME_WORD.match(w) for w in words):
        return None
    if len(words[0]) < 2 or len(words[-1]) < 2:
        return None
    return words[0], words[-1]


SEPARATORS = re.compile(r"\s*(?:,|\||–|—|-|:|/)\s+|\s+(?:–|—|-)\s*")


def people_on(page: Page, titles: list[str]) -> list[dict]:
    """Names next to a matching job title: 'Jane Smith, Finance Director' or a name line beside a title line."""
    found: list[dict] = []
    lines = page.lines
    for i, line in enumerate(lines):
        if len(line) > 140:
            continue
        hit = _title_hit(line, titles)
        if not hit:
            continue
        name = None
        parts = [p for p in SEPARATORS.split(line) if p]
        for p in parts:
            if not _title_hit(p, titles):
                name = clean_name(p)
                if name:
                    break
        if not name:
            for j in (i - 1, i + 1, i - 2):
                if 0 <= j < len(lines) and len(lines[j]) <= 60 and not _title_hit(lines[j], titles):
                    name = clean_name(lines[j])
                    if name:
                        break
        if name:
            title = next((p for p in parts if _title_hit(p, titles)), line)[:80]
            found.append({"first_name": name[0], "last_name": name[1], "title": title, "matched": hit,
                          "evidence_url": page.url})
    return found
