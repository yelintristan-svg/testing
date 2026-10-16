"""Polite web fetching for prospecting: robots.txt, a gap between requests, a clear user agent.

Everything that touches the network takes a `get` function so tests can swap
in canned responses. `get(url, headers)` returns (status, final_url, text);
status 0 means the request failed before an HTTP answer came back.
"""
from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from typing import Callable

Get = Callable[[str, dict], "tuple[int, str, str]"]
MAX_BYTES = 1_500_000


def http_get(url: str, headers: dict, timeout: int = 15) -> tuple[int, str, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (http/https only, see Polite.get)
            ctype = r.headers.get("Content-Type", "")
            if not any(t in ctype for t in ("text/", "json", "xml")):
                return r.status, r.geturl(), ""
            charset = r.headers.get_content_charset() or "utf-8"
            return r.status, r.geturl(), r.read(MAX_BYTES).decode(charset, "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, ""
    except (urllib.error.URLError, OSError, ValueError):
        return 0, url, ""


def host_of(url: str) -> str:
    h = (urllib.parse.urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


class Polite:
    """Fetch public web pages the way a well-behaved crawler does.

    * reads each site's robots.txt and skips anything it disallows for us,
    * waits `gap` seconds between requests to the same site,
    * says who we are in the User-Agent, with a contact address.
    """

    def __init__(self, user_agent: str, gap: float = 3.0, get: Get = http_get,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        self.ua, self.gap, self._get, self._sleep, self._clock = user_agent, gap, get, sleep, clock
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last: dict[str, float] = {}
        self.requests = 0

    def _wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            delay = self.gap - (self._clock() - last)
            if delay > 0:
                self._sleep(delay)
        self._last[host] = self._clock()

    def _fetch(self, url: str) -> tuple[int, str, str]:
        self._wait(host_of(url))
        self.requests += 1
        return self._get(url, {"User-Agent": self.ua, "Accept": "text/html,application/xhtml+xml"})

    def allowed(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            status, _, text = self._fetch(origin + "/robots.txt")
            if status == 0 or status >= 500:
                rp = None                      # site unreachable or erroring: treat as "keep out"
            else:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(text.splitlines() if status == 200 else [])
            self._robots[origin] = rp
        rp = self._robots[origin]
        return rp is not None and rp.can_fetch(self.ua, url)

    def get(self, url: str) -> tuple[int, str, str] | None:
        """(status, final_url, text), or None if robots.txt says no or the URL isn't http(s)."""
        if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
            return None
        if not self.allowed(url):
            return None
        return self._fetch(url)
