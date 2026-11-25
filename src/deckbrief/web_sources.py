"""Fetching a company website as citable sources.

Live fetches go through `SafeFetcher`, which refuses non-public addresses (the agent can ask
for URLs after reading untrusted text, so this matters) and caps size and redirects. The
bundled samples use `SnapshotFetcher`, which serves saved HTML for fictional `.example` sites.
"""

from __future__ import annotations

import ipaddress
import json
import socket
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlparse

import httpx

from deckbrief.models import Source

MAX_BYTES = 1_500_000
MAX_TEXT = 6000
INTERESTING = ("about", "team", "company", "impact", "customers", "product", "sustainab")


class FetchError(RuntimeError):
    pass


class Fetcher(Protocol):
    def get(self, url: str) -> tuple[str, str]:
        """Return (final_url, html)."""
        ...


def assert_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FetchError(f"not an http(s) URL: {url}")
    host = parsed.hostname
    try:
        addrs = {str(i[4][0]) for i in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)}
    except OSError as exc:
        raise FetchError(f"could not resolve {host}") from exc
    for a in addrs:
        ip = ipaddress.ip_address(a)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError(f"{host} resolves to a non-public address")


class SafeFetcher:
    def __init__(self, timeout: float = 10.0, max_redirects: int = 4):
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": "deckbrief/0.1 (student project; first-pass screening)"},
        )
        self.max_redirects = max_redirects

    def get(self, url: str) -> tuple[str, str]:
        current = url
        for _ in range(self.max_redirects + 1):
            assert_public(current)
            try:
                resp = self.client.get(current)
            except httpx.HTTPError as exc:
                raise FetchError(f"request failed: {exc}") from exc
            if resp.is_redirect and "location" in resp.headers:
                current = urljoin(current, resp.headers["location"])
                continue
            if resp.status_code >= 400:
                raise FetchError(f"HTTP {resp.status_code} for {current}")
            if "html" not in resp.headers.get("content-type", "html"):
                raise FetchError(f"not an HTML page: {current}")
            return current, resp.content[:MAX_BYTES].decode(resp.encoding or "utf-8", "replace")
        raise FetchError("too many redirects")


class SnapshotFetcher:
    """Serves saved pages from a JSON file of {url: html}. Used for the fictional samples."""

    def __init__(self, path: Path):
        self.pages: dict[str, str] = json.loads(path.read_text())

    def get(self, url: str) -> tuple[str, str]:
        for candidate in (url, url.rstrip("/"), url.rstrip("/") + "/"):
            if candidate in self.pages:
                return candidate, self.pages[candidate]
        raise FetchError(f"not in snapshot: {url}")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag in {"p", "br", "li", "h1", "h2", "h3", "div", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str, str, list[str]]:
    """Return (title, visible text, hrefs)."""
    p = _TextExtractor()
    p.feed(html)
    lines = [" ".join(line.split()) for line in "".join(p.parts).splitlines()]
    text = "\n".join(line for line in lines if line)
    return " ".join(p.title.split()), text[:MAX_TEXT], p.links


def page_source(fetcher: Fetcher, url: str) -> tuple[Source, list[str]]:
    final, html = fetcher.get(url)
    title, text, links = html_to_text(html)
    src = Source(id=final, kind="web", label=title or final, text=text, url=final)
    return src, [urljoin(final, h) for h in links]


def same_site(a: str, b: str) -> bool:
    ha, hb = urlparse(a).hostname or "", urlparse(b).hostname or ""
    return ha.removeprefix("www.") == hb.removeprefix("www.")


def fetch_website(fetcher: Fetcher, url: str, max_pages: int = 4) -> tuple[list[Source], list[str]]:
    """Fetch the homepage plus a few likely-useful pages on the same site.

    Returns (sources, warnings). Failures are warnings, not errors: the deck alone is enough
    to produce a brief.
    """
    if "://" not in url:
        url = "https://" + url
    warnings: list[str] = []
    try:
        home, links = page_source(fetcher, url)
    except FetchError as exc:
        return [], [f"Website not used: {exc}"]
    sources = [home]
    seen = {home.id}
    for link in links:
        if len(sources) >= max_pages:
            break
        clean = link.split("#")[0]
        if clean in seen or not same_site(clean, home.id):
            continue
        if not any(k in clean.lower() for k in INTERESTING):
            continue
        seen.add(clean)
        try:
            src, _ = page_source(fetcher, clean)
        except FetchError as exc:
            warnings.append(f"Skipped {clean}: {exc}")
            continue
        if src.id not in {s.id for s in sources}:
            sources.append(src)
    return sources, warnings
