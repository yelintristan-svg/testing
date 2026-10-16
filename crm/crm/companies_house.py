"""Companies House Public Data API: UK companies by area, industry and size, and their officers.

Free. Register at https://developer.company-information.service.gov.uk/, create
an application, add a REST API key and set COMPANIES_HOUSE_API_KEY. The API
allows 600 requests every five minutes; we stay under that with a gap.

What it gives us:
* advanced search: active companies filtered by registered-office location,
  SIC codes (industry), company type and incorporation date,
* the company profile: the type of the latest accounts filed, which is the
  only size signal on the register (see SIZE_ACCOUNTS),
* officers: directors and secretaries, with the occupation they gave, which
  often reads "Finance Director" or "Chartered Accountant".

The register holds no emails, phone numbers or employee counts.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.parse
from datetime import date
from typing import Callable

from . import net

BASE = "https://api.company-information.service.gov.uk"

# Size, read from the type of the latest accounts. UK thresholds (from April
# 2025): micro up to 10 staff, small up to 50, medium up to 250. Small and
# micro companies both often file abridged or "total exemption" accounts, so
# "small" also lets some micro companies through; the website and people
# checks weed most of them out.
SIZE_ACCOUNTS = {
    "micro": {"micro-entity"},
    "small": {"small", "total-exemption-full", "total-exemption-small", "unaudited-abridged",
              "audited-abridged", "partial-exemption"},
    "medium": {"medium"},
    "large": {"full", "group"},
}

OFFICER_ROLES = {"director", "secretary", "llp-member", "llp-designated-member"}


def size_of(profile: dict) -> str:
    kind = ((profile.get("accounts") or {}).get("last_accounts") or {}).get("type") or ""
    for size, kinds in SIZE_ACCOUNTS.items():
        if kind in kinds:
            return size
    return "unknown"


def split_officer_name(name: str) -> tuple[str, str]:
    """'SMITH, Jane Mary' -> ('Jane', 'Smith'). Drops honorifics."""
    last, _, rest = name.partition(",")
    words = [w for w in rest.replace(".", " ").split()
             if w.lower() not in {"mr", "mrs", "ms", "miss", "dr", "sir", "dame", "prof", "lord", "lady"}]
    first = words[0] if words else ""
    return first.title(), last.strip().title()


class CompaniesHouse:
    def __init__(self, api_key: str, get: net.Get = net.http_get, gap: float = 0.6,
                 sleep: Callable[[float], None] = time.sleep):
        token = base64.b64encode(f"{api_key}:".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}", "Accept": "application/json"}
        self._get, self.gap, self._sleep = get, gap, sleep
        self.requests = 0

    def _json(self, path: str, params: dict | None = None) -> dict | None:
        if self.requests:
            self._sleep(self.gap)
        self.requests += 1
        q = ("?" + urllib.parse.urlencode(params, doseq=True)) if params else ""
        status, _, text = self._get(f"{BASE}{path}{q}", self.headers)
        if status == 404:
            return None
        if status == 401:
            raise RuntimeError("Companies House rejected the API key (check COMPANIES_HOUSE_API_KEY).")
        if status == 429:
            raise RuntimeError("Companies House rate limit reached; the rest waits for the next run.")
        if status != 200:
            raise RuntimeError(f"Companies House returned {status} for {path}")
        return json.loads(text or "{}")

    def search(self, *, location: str = "", sic_codes=(), company_types=("ltd", "plc", "llp"),
               min_age_years: int = 0, start_index: int = 0, size: int = 50, today: date | None = None
               ) -> tuple[list[dict], int]:
        params: dict = {"company_status": "active", "size": size, "start_index": start_index}
        if location:
            params["location"] = location
        if sic_codes:
            params["sic_codes"] = ",".join(sic_codes)
        if company_types:
            params["company_type"] = ",".join(company_types)
        if min_age_years:
            t = today or date.today()
            params["incorporated_to"] = t.replace(year=t.year - min_age_years, day=min(t.day, 28)).isoformat()
        data = self._json("/advanced-search/companies", params) or {}
        return data.get("items") or [], int(data.get("hits") or 0)

    def profile(self, number: str) -> dict:
        return self._json(f"/company/{urllib.parse.quote(number)}") or {}

    def officers(self, number: str) -> list[dict]:
        """Current officers who are people (not corporate secretaries), with name split."""
        data = self._json(f"/company/{urllib.parse.quote(number)}/officers",
                          {"items_per_page": 100, "register_view": "false"}) or {}
        out = []
        for o in data.get("items") or []:
            if o.get("resigned_on") or o.get("officer_role") not in OFFICER_ROLES:
                continue
            first, last = split_officer_name(o.get("name") or "")
            if first and last:
                out.append({"first_name": first, "last_name": last, "role": o["officer_role"],
                            "occupation": (o.get("occupation") or "").strip()})
        return out
