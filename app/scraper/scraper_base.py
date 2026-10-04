"""Common interface for crosshair sources and a polite HTTP client.

Every source (website API, file, manual list) is an adapter that produces
``SourceRecord`` objects. Adapters only collect candidate data with provenance;
they never influence recommendations.

The HTTP client enforces responsible access:
* identifying User-Agent with contact information (required, never generic)
* robots.txt check before the first request to a host
* minimum interval between requests (per client)
* on-disk response cache with a TTL so repeated updates re-use results
* no retries that hammer a server; errors are raised and reported
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.robotparser
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import requests

from app import __version__
from app.data.models import ImportMethod
from app.utils.logging import get_logger

log = get_logger("scraper")

ProgressCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]


class ScraperError(RuntimeError):
    """A source could not be fetched (network, policy, or format problem)."""


class ScrapeCancelled(ScraperError):
    """The user cancelled an update."""


@dataclass(frozen=True)
class SourceRecord:
    """One crosshair code with provenance, as obtained from a source."""

    code: str
    source_name: str
    import_method: ImportMethod
    source_url: str | None = None
    source_player: str | None = None
    source_date: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    records: list[SourceRecord] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    requests_made: int = 0
    cache_hits: int = 0


class SourceAdapter(ABC):
    """Interface implemented by every crosshair source."""

    name: str

    @abstractmethod
    def fetch(
        self,
        progress: ProgressCallback | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> FetchResult:
        """Collect records. Must not write to the database."""


def build_user_agent(contact: str) -> str:
    contact = contact.strip()
    if "@" not in contact and not contact.startswith("http"):
        raise ScraperError(
            "A contact e-mail address or URL is required in the User-Agent "
            "(source operators ask for this so they can reach you)."
        )
    return f"CrosshairResearchPrototype/{__version__} (university HCI research prototype; {contact})"


class PoliteHttpClient:
    def __init__(
        self,
        user_agent: str,
        cache_dir: Path,
        min_interval_s: float,
        cache_ttl_s: float,
        force_refresh: bool = False,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout_s: float = 30.0,
    ) -> None:
        self.user_agent = user_agent
        self.cache_dir = cache_dir
        self.min_interval_s = min_interval_s
        self.cache_ttl_s = cache_ttl_s
        self.force_refresh = force_refresh
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip"})
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.timeout_s = timeout_s
        self.requests_made = 0
        self.cache_hits = 0

    # ------------------------------------------------------------------ cache
    def _cache_path(self, url: str, params: Mapping[str, Any]) -> Path:
        key = url + "?" + urlencode(sorted((k, str(v)) for k, v in params.items()))
        return self.cache_dir / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")

    def _read_cache(self, path: Path) -> Any | None:
        if self.force_refresh or not path.exists():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            fetched = datetime.fromisoformat(entry["fetched_at"])
        except (OSError, ValueError, KeyError) as exc:
            log.warning("cache_unreadable path=%s error=%s", path, exc)
            return None
        age = (datetime.now(timezone.utc) - fetched).total_seconds()
        return entry["data"] if age <= self.cache_ttl_s else None

    def _write_cache(self, path: Path, url: str, params: Mapping[str, Any], data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "params": dict(params),
            "user_agent": self.user_agent,
            "data": data,
        }
        path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")

    # ----------------------------------------------------------------- policy
    def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        parser = self._robots.get(origin)
        if parser is None:
            parser = urllib.robotparser.RobotFileParser()
            response = self._send(origin + "/robots.txt", {})
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            elif response.status_code in (401, 403):
                raise ScraperError(f"{origin}/robots.txt is forbidden ({response.status_code}).")
            else:
                parser.parse([])
            self._robots[origin] = parser
        if not parser.can_fetch(self.user_agent, url):
            raise ScraperError(f"robots.txt of {origin} disallows {parts.path}.")

    def _wait_for_slot(self) -> None:
        if self._last_request is not None:
            remaining = self.min_interval_s - (self._clock() - self._last_request)
            if remaining > 0:
                self._sleep(remaining)

    def _send(self, url: str, params: Mapping[str, Any]) -> requests.Response:
        self._wait_for_slot()
        try:
            response = self.session.get(url, params=dict(params), timeout=self.timeout_s)
        except requests.RequestException as exc:
            raise ScraperError(f"Request to {url} failed: {exc}") from exc
        finally:
            self._last_request = self._clock()
            self.requests_made += 1
        log.info("http_get url=%s status=%s", url, response.status_code)
        return response

    # -------------------------------------------------------------------- api
    def get_json(self, url: str, params: Mapping[str, Any]) -> Any:
        path = self._cache_path(url, params)
        cached = self._read_cache(path)
        if cached is not None:
            self.cache_hits += 1
            return cached
        self._check_robots(url)
        response = self._send(url, params)
        if response.status_code == 429:
            raise ScraperError("The source is rate limiting this client (HTTP 429). Try later.")
        if response.status_code != 200:
            raise ScraperError(f"{url} returned HTTP {response.status_code}.")
        try:
            data = response.json()
        except ValueError as exc:
            raise ScraperError(f"{url} did not return JSON.") from exc
        self._write_cache(path, url, params, data)
        return data
