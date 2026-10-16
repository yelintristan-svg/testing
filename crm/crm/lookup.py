"""Find a work email for a person through a compliant data provider.

Providers here sell business contact data under their own terms and DPAs,
and return a verification status. This module never visits LinkedIn or
scrapes websites: it sends a name plus company (and, for Apollo, a profile
URL as a matching key) to the provider's API and reads back what it holds.

Every result goes through `check()` before it reaches the CRM:
* the provider must say the address is verified (deliverable),
* it must be on the company's own domain (a work address), never a
  personal one (gmail etc.): PECR lets us email corporate subscribers
  without consent, not individuals,
* the person must not be on the suppression list (checked on import).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from . import compliance

Fetch = Callable[[urllib.request.Request], dict]


def _http_json(req: urllib.request.Request) -> dict:
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (fixed https hosts)
        return json.loads(r.read().decode())


@dataclass
class Found:
    email: str
    verified: bool
    status: str           # provider's own wording, kept for the audit log
    provider: str
    source_detail: str    # shown to the person in the first email (UK GDPR Art. 14)
    company_domain: str = ""  # provider's view of the employer's domain, if it has one


class Apollo:
    """Apollo People Match (POST /api/v1/people/match). Works on the free plan's credits."""
    name = "apollo"
    source_detail = "a business contact database (Apollo.io)"

    def __init__(self, api_key: str, fetch: Fetch = _http_json):
        self.key, self.fetch = api_key, fetch

    def find(self, first_name, last_name, company, domain, profile_url) -> Found | None:
        body = {k: v for k, v in {"first_name": first_name, "last_name": last_name, "organization_name": company,
                                  "domain": domain, "linkedin_url": profile_url,
                                  "reveal_personal_emails": False}.items() if v not in (None, "")}
        req = urllib.request.Request(
            "https://api.apollo.io/api/v1/people/match", data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "X-Api-Key": self.key, "Cache-Control": "no-cache"})
        person = (self.fetch(req) or {}).get("person") or {}
        email = person.get("email")
        if not email:
            return None
        status = person.get("email_status") or "unknown"
        org_domain = ((person.get("organization") or {}).get("primary_domain")) or ""
        return Found(email, status == "verified", status, self.name, self.source_detail, org_domain)


class ApolloSearch:
    """Apollo People API Search (no credits, no emails) plus People Match by id (1 credit per email).

    Used when prospecting.toml sets source = "apollo". Apollo's docs say the
    search endpoint may need a master API key.
    """

    def __init__(self, api_key: str, fetch: Fetch = _http_json):
        self.key, self.fetch = api_key, fetch

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"https://api.apollo.io/api/v1/{path}", data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "X-Api-Key": self.key, "Cache-Control": "no-cache"})
        return self.fetch(req) or {}

    def search(self, titles: list[str], locations: list[str], employee_ranges: list[str], page: int) -> list[dict]:
        body = {"person_titles": titles, "include_similar_titles": False, "person_locations": locations,
                "organization_num_employees_ranges": employee_ranges, "page": page, "per_page": 25}
        return self._post("mixed_people/api_search", body).get("people") or []

    def reveal(self, person_id: str) -> dict:
        return self._post("people/match", {"id": person_id, "reveal_personal_emails": False}).get("person") or {}


class Hunter:
    """Hunter Email Finder (GET /v2/email-finder). Needs a company domain."""
    name = "hunter"
    source_detail = "a business email finder (Hunter.io) using your company's public email format"

    def __init__(self, api_key: str, fetch: Fetch = _http_json):
        self.key, self.fetch = api_key, fetch

    def find(self, first_name, last_name, company, domain, profile_url) -> Found | None:
        if not domain:
            return None
        q = urllib.parse.urlencode({"domain": domain, "first_name": first_name, "last_name": last_name or "",
                                    "api_key": self.key})
        data = (self.fetch(urllib.request.Request(f"https://api.hunter.io/v2/email-finder?{q}")) or {}).get("data") or {}
        email = data.get("email")
        if not email:
            return None
        status = ((data.get("verification") or {}).get("status")) or "unknown"
        return Found(email, status == "valid", status, self.name, self.source_detail, domain)


def provider_from_settings(settings, fetch: Fetch = _http_json):
    if settings.email_provider == "apollo":
        if not settings.apollo_api_key:
            raise RuntimeError("Set APOLLO_API_KEY to use Apollo lookups.")
        return Apollo(settings.apollo_api_key, fetch)
    if settings.email_provider == "hunter":
        if not settings.hunter_api_key:
            raise RuntimeError("Set HUNTER_API_KEY to use Hunter lookups.")
        return Hunter(settings.hunter_api_key, fetch)
    return None


def check(found: Found | None, company_domain: str | None) -> tuple[bool, str]:
    """(usable, reason). Only verified work addresses pass."""
    if found is None:
        return False, "not_found"
    if not found.verified:
        return False, f"unverified_{found.status}"
    e = compliance.normalise_email(found.email)
    domain = e.rpartition("@")[2]
    if domain in compliance.PERSONAL_DOMAINS:
        return False, "personal_address"
    cd = company_domain.lower().strip() if company_domain else ""
    if cd and not (domain == cd or domain.endswith("." + cd)):
        return False, "not_company_domain"
    return True, "ok"
