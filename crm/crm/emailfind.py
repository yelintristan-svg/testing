"""Work out someone's work email from what their company publishes, then check it.

How sure we are, best first (the `status` on each result):

* published: the exact address appears on the company's own website.
* verified:  the company's mail server accepted the address when asked
             (SMTP RCPT, nothing sent) and does not accept made-up addresses.
* pattern:   another named person's published address shows the company's
             format (e.g. jane.smith@), applied to this person. The domain
             takes mail (MX record).
* guess:     only the most common UK format. Not used unless you allow it.

Mail server checks are kept polite: one connection per company, a made-up
address first to spot "accept everything" servers, at most a few addresses,
no message is ever sent (we QUIT before DATA). Home broadband and most cloud
hosts block outgoing port 25; when that happens the check switches itself off
for the run and results fall back to published/pattern.
"""
from __future__ import annotations

import json
import secrets
import smtplib
import socket
import unicodedata
import urllib.parse
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from . import net

# Most common UK business formats first.
PATTERNS = ["{first}.{last}", "{first}", "{f}{last}", "{first}{last}", "{f}.{last}", "{first}_{last}",
            "{first}{l}", "{first}-{last}", "{last}.{first}", "{last}{f}", "{last}"]
GENERIC = {"info", "hello", "enquiries", "enquiry", "sales", "accounts", "admin", "office", "contact", "support",
           "careers", "jobs", "hr", "finance", "reception", "mail", "team", "privacy", "dpo", "marketing",
           "recruitment", "noreply", "no-reply", "help", "service", "customerservice", "orders", "general",
           "invoices", "payments", "webmaster", "press", "media", "accountspayable", "purchasing", "gdpr"}


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalpha())


def locals_for(first: str, last: str) -> dict[str, str]:
    f, l = _ascii(first), _ascii(last.split("-")[0] if "-" in last and len(last) > 12 else last)
    if not f or not l:
        return {}
    vals = {"first": f, "last": l, "f": f[0], "l": l[0]}
    return {p: p.format(**vals) for p in PATTERNS}


def infer_pattern(emails: set[str], people: list[tuple[str, str]]) -> str | None:
    """The format used by the most published addresses that match a named person."""
    votes: Counter = Counter()
    for e in emails:
        local = e.partition("@")[0]
        if local in GENERIC:
            continue
        for first, last in people:
            for pat, value in locals_for(first, last).items():
                if value == local and (pat not in ("{first}", "{last}") or len(local) > 3):
                    votes[pat] += 1
                    break
    return votes.most_common(1)[0][0] if votes else None


# -- DNS: MX records over HTTPS (no extra packages) ---------------------------

def mx_hosts(domain: str, get: net.Get = net.http_get) -> list[str]:
    q = urllib.parse.urlencode({"name": domain, "type": "MX"})
    status, _, text = get(f"https://cloudflare-dns.com/dns-query?{q}", {"Accept": "application/dns-json"})
    if status != 200:
        return []
    answers = []
    for a in (json.loads(text or "{}").get("Answer") or []):
        if a.get("type") != 15:
            continue
        pref, _, host = str(a.get("data", "")).partition(" ")
        host = host.strip().rstrip(".")
        if host:                                   # "0 ." is a null MX: the domain takes no mail
            answers.append((int(pref or 0), host))
    return [h for _, h in sorted(answers)]


# -- SMTP check ---------------------------------------------------------------

class SmtpUnavailable(Exception):
    """Port 25 is blocked from here, or the server wouldn't talk."""


@dataclass
class Probe:
    catch_all: bool
    results: dict[str, int]       # address -> SMTP reply code to RCPT TO


class SmtpProber:
    def __init__(self, helo: str, mail_from: str, connect: Callable = smtplib.SMTP, timeout: int = 12,
                 budget: int = 60):
        self.helo, self.mail_from, self._connect, self.timeout, self.budget = helo, mail_from, connect, timeout, budget
        self.used = 0
        self.connected = False     # one success shows port 25 is open from here
        self.disabled = False

    def probe(self, mx: list[str], domain: str, addresses: list[str]) -> Probe:
        addresses = addresses[: max(0, self.budget - self.used - 1)]
        if not addresses:
            raise SmtpUnavailable("daily SMTP check budget used up")
        last_err: Exception | None = None
        for host in mx[:2]:
            try:
                s = self._connect(host, 25, timeout=self.timeout)
            except (OSError, smtplib.SMTPException, socket.timeout) as e:
                last_err = e
                continue
            self.connected = True
            try:
                s.ehlo(self.helo)
                code, _ = s.mail(self.mail_from)
                if code >= 400:
                    raise SmtpUnavailable(f"{host} refused MAIL FROM ({code})")
                fake = f"zz-{secrets.token_hex(5)}@{domain}"
                self.used += 1
                fake_code, _ = s.rcpt(fake)
                results: dict[str, int] = {}
                if fake_code >= 300:               # it rejects made-up addresses, so answers mean something
                    for a in addresses:
                        self.used += 1
                        results[a], _ = s.rcpt(a)
                        if results[a] in (250, 251):
                            break
                return Probe(fake_code in (250, 251), results)
            except (OSError, smtplib.SMTPException) as e:
                last_err = e
            finally:
                try:
                    s.quit()
                except Exception:  # noqa: BLE001
                    pass
        if not self.connected:     # never got through: outgoing port 25 is blocked here
            self.disabled = True
        raise SmtpUnavailable(str(last_err) if last_err else "no mail server")


# -- putting it together ------------------------------------------------------

@dataclass
class Guess:
    email: str
    status: str          # published | verified | pattern | guess | rejected
    detail: str = ""


def find(first: str, last: str, domain: str, published: set[str], anchors: list[tuple[str, str]],
         mx: list[str], prober: SmtpProber | None) -> Guess | None:
    """Best address for one person at `domain`, or None if the domain takes no mail."""
    options = locals_for(first, last)
    if not options:
        return None
    for pat, local in options.items():
        addr = f"{local}@{domain}"
        if addr in published and (pat not in ("{first}", "{last}") or len(local) > 3):
            return Guess(addr, "published", "listed on the company's website")
    if not mx:
        return None
    pattern = infer_pattern(published, anchors)
    ordered = ([pattern] if pattern else []) + [p for p in PATTERNS[:4] if p != pattern]
    tries = [f"{options[p]}@{domain}" for p in ordered]
    pr = None
    if prober is not None and not prober.disabled:
        try:
            pr = prober.probe(mx, domain, tries[:3])
        except SmtpUnavailable:
            pr = None
        if pr and not pr.catch_all:
            for a, code in pr.results.items():
                if code in (250, 251):
                    return Guess(a, "verified", "mail server accepted it")
            if pr.results and all(c >= 500 for c in pr.results.values()):
                return Guess(tries[0], "rejected", "mail server rejected the likely formats")
    if pattern:
        return Guess(tries[0], "pattern", f"company format {pattern}")
    return Guess(tries[0], "guess", "most common format")
