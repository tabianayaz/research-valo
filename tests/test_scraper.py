"""Scraper tests. No network access: HTTP is replaced by a deterministic fake."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.data.models import ImportMethod
from app.data.repository import Repository
from app.scraper.crosshair_scraper import LIQUIPEDIA_API, LiquipediaCrosshairAdapter
from app.scraper.importer import ImportStatus, import_records, parse_manual_line
from app.scraper.parsers import extract_templates
from app.scraper.scraper_base import (
    PoliteHttpClient,
    ScrapeCancelled,
    ScraperError,
    build_user_agent,
)

RANGES = {"size": (1, 20), "thickness": (1, 10), "gap": (0, 20),
          "outline_thickness": (1, 6), "opacity": (0.05, 1.0)}
UA = build_user_agent("researcher@example.org")


class FakeResponse:
    def __init__(self, status: int = 200, data=None, text: str = "") -> None:
        self.status_code = status
        self._data = data
        self.text = text

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


class FakeSession:
    """Routes requests to a handler; records every call."""

    def __init__(self, handler, robots: str = "User-agent: *\nDisallow:\n") -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[tuple[str, dict]] = []
        self.handler = handler
        self.robots = robots

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        if url.endswith("/robots.txt"):
            return FakeResponse(200, text=self.robots)
        return self.handler(url, params or {})


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def make_client(tmp_path: Path, handler, robots: str | None = None, **kwargs) -> tuple[PoliteHttpClient, FakeSession, FakeClock]:
    session = FakeSession(handler, robots) if robots is not None else FakeSession(handler)
    clock = FakeClock()
    client = PoliteHttpClient(
        user_agent=UA, cache_dir=tmp_path / "cache", min_interval_s=2.5,
        cache_ttl_s=3600, session=session, sleep=clock.sleep, clock=clock, **kwargs,
    )
    return client, session, clock


# ------------------------------------------------------------- wikitext parsing
def test_extract_templates_handles_names_nesting_and_case() -> None:
    wikitext = (
        "intro {{Infobox player|name=X}}\n"
        "{{CrosshairTable|sharecode=0;P;0l;4|date=2024-08-01|ref={{cite web|url=a|title=b}}}}\n"
        "{{crosshair_table\n|date=2023-05-21\n|color=blue\n|innerlength=2\n}}\n"
        "{{crosshairtable|sharecode= 0;P;d;1;0b;0 |ref=[[Link|text]]}}"
    )
    tables = extract_templates(wikitext, {"CrosshairTable", "Crosshair table"})
    assert len(tables) == 3
    assert tables[0]["sharecode"] == "0;P;0l;4"
    assert tables[0]["ref"] == "{{cite web|url=a|title=b}}"
    assert tables[1]["color"] == "blue"
    assert "sharecode" not in tables[1]
    assert tables[2]["sharecode"] == "0;P;d;1;0b;0"
    assert tables[2]["ref"] == "[[Link|text]]"


def test_extract_templates_unclosed_is_ignored() -> None:
    assert extract_templates("{{CrosshairTable|sharecode=0;P", {"CrosshairTable"}) == []


# --------------------------------------------------------------- manual lines
@pytest.mark.parametrize(
    "line, expected",
    [
        ("0;P;0l;4", ("0;P;0l;4", None, None)),
        ("aspas, 0;P;0l;4", ("0;P;0l;4", "aspas", None)),
        ("aspas\t0;P;0l;4\thttps://example.org/x", ("0;P;0l;4", "aspas", "https://example.org/x")),
        ("0;P;0l;4, TenZ", ("0;P;0l;4", "TenZ", None)),
    ],
)
def test_parse_manual_line(line: str, expected) -> None:
    parsed = parse_manual_line(line)
    assert (parsed.code, parsed.player, parsed.url) == expected


def test_parse_manual_line_skips_blank_and_comments() -> None:
    assert parse_manual_line("   ") is None
    assert parse_manual_line("# comment") is None


def test_parse_manual_line_without_code_passes_text_through() -> None:
    assert parse_manual_line("player,code,source_url").code == "player,code,source_url"


# ---------------------------------------------------------------- HTTP client
def test_user_agent_requires_contact() -> None:
    with pytest.raises(ScraperError):
        build_user_agent("")
    assert "researcher@example.org" in UA


def test_rate_limit_enforced_between_requests(tmp_path: Path) -> None:
    client, session, clock = make_client(tmp_path, lambda u, p: FakeResponse(200, {"ok": p["n"]}))
    client.get_json("https://x.test/api", {"n": 1})
    client.get_json("https://x.test/api", {"n": 2})
    # robots.txt, request 1, request 2 -> two waits of 2.5 s
    assert len(session.calls) == 3
    assert clock.slept == [2.5, 2.5]


def test_cache_reused(tmp_path: Path) -> None:
    client, session, _ = make_client(tmp_path, lambda u, p: FakeResponse(200, {"v": 1}))
    assert client.get_json("https://x.test/api", {"a": 1}) == {"v": 1}
    assert client.get_json("https://x.test/api", {"a": 1}) == {"v": 1}
    assert client.cache_hits == 1
    assert len([c for c in session.calls if c[0] == "https://x.test/api"]) == 1


def test_force_refresh_bypasses_cache(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path, lambda u, p: FakeResponse(200, {"v": 1}))
    client.get_json("https://x.test/api", {"a": 1})
    refresher, session, _ = make_client(tmp_path, lambda u, p: FakeResponse(200, {"v": 2}),
                                        force_refresh=True)
    assert refresher.get_json("https://x.test/api", {"a": 1}) == {"v": 2}


def test_robots_disallow_blocks_request(tmp_path: Path) -> None:
    client, session, _ = make_client(tmp_path, lambda u, p: FakeResponse(200, {}),
                                     robots="User-agent: *\nDisallow: /api\n")
    with pytest.raises(ScraperError, match="robots.txt"):
        client.get_json("https://x.test/api", {})
    assert [c[0] for c in session.calls] == ["https://x.test/robots.txt"]


@pytest.mark.parametrize("status", [403, 429, 500])
def test_http_errors_raise(tmp_path: Path, status: int) -> None:
    client, _, _ = make_client(tmp_path, lambda u, p: FakeResponse(status))
    with pytest.raises(ScraperError):
        client.get_json("https://x.test/api", {})


# ---------------------------------------------------------- Liquipedia adapter
PAGE_WITH_CODES = (
    "{{Infobox player|name=Alpha}}\n"
    "{{CrosshairTable|sharecode=0;P;c;5;h;0;0l;4;0o;2;0a;1;0f;0;1b;0|date=2024-08-01|ref=player}}"
)
PAGE_OLD_FORMAT = "{{crosshair table\n|date=2023-05-21\n|color=blue\n|innerlength=2\n}}"


def liquipedia_handler(url: str, params: dict) -> FakeResponse:
    assert url == LIQUIPEDIA_API
    assert params.get("action") == "query"
    if params.get("list") == "embeddedin":
        if params["eititle"] == "Template:CrosshairTable":
            return FakeResponse(200, {"query": {"embeddedin": [{"ns": 0, "title": "Alpha"}]}})
        return FakeResponse(200, {"query": {"embeddedin": [{"ns": 0, "title": "Beta"}]}})
    assert params["titles"] == "Alpha|Beta"
    return FakeResponse(200, {"query": {"pages": [
        {"title": "Alpha", "revisions": [{"revid": 111, "timestamp": "2026-01-01T00:00:00Z",
                                           "slots": {"main": {"content": PAGE_WITH_CODES}}}]},
        {"title": "Beta", "revisions": [{"revid": 222, "timestamp": "2026-01-02T00:00:00Z",
                                          "slots": {"main": {"content": PAGE_OLD_FORMAT}}}]},
    ]}})


def test_liquipedia_adapter_extracts_records(tmp_path: Path) -> None:
    client, session, _ = make_client(tmp_path, liquipedia_handler)
    result = LiquipediaCrosshairAdapter(client).fetch()
    assert len(result.records) == 1
    record = result.records[0]
    assert record.source_player == "Alpha"
    assert record.import_method == ImportMethod.SCRAPER
    assert "oldid=111" in record.source_url
    assert record.source_date == "2024-08-01"
    assert record.extra["license"] == "CC-BY-SA 3.0"
    assert len(result.skipped) == 1 and "Beta" in result.skipped[0]
    assert all(c[1].get("action") != "parse" for c in session.calls if c[0] == LIQUIPEDIA_API)
    assert all(c[1].get("einamespace") == 0 for c in session.calls if c[1].get("list") == "embeddedin")


def test_liquipedia_api_error_raises(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path, lambda u, p: FakeResponse(200, {"error": {"code": "x"}}))
    with pytest.raises(ScraperError, match="API error"):
        LiquipediaCrosshairAdapter(client).fetch()


def test_liquipedia_cancel(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path, liquipedia_handler)
    with pytest.raises(ScrapeCancelled):
        LiquipediaCrosshairAdapter(client).fetch(should_cancel=lambda: True)


def test_adapter_records_import_with_provenance(tmp_path: Path, repo: Repository) -> None:
    client, _, _ = make_client(tmp_path, liquipedia_handler)
    records = LiquipediaCrosshairAdapter(client).fetch().records
    outcomes = import_records(repo, records, RANGES)
    assert [o.status for o in outcomes] == [ImportStatus.IMPORTED]
    listing = repo.list_source_listings()[0]
    assert listing.source.source_player == "Alpha"
    assert listing.source.import_method == ImportMethod.SCRAPER
    assert listing.source.raw_payload["source_record"]["extra"]["revision_id"] == 111
    assert import_records(repo, records, RANGES)[0].status == ImportStatus.DUPLICATE
