"""Source adapters for publicly available crosshair codes.

LiquipediaCrosshairAdapter
--------------------------
Reads VALORANT crosshair share codes from Liquipedia player pages through the
MediaWiki API only (Liquipedia does not permit automated access to its HTML
pages). Terms followed (https://liquipedia.net/api-terms-of-use):

* at most 1 request per 2 seconds (this adapter waits >= 2.5 s); no
  ``action=parse`` calls are used
* identifying User-Agent with contact information, gzip accepted
* responses cached and re-used (default 7 days)
* content is CC-BY-SA 3.0: every record keeps a permalink (``oldid``) for
  attribution

Only pages in the main (article) namespace are used; user drafts are skipped.
Only ``CrosshairTable`` transclusions with a ``sharecode`` are imported. Older
``Crosshair table`` transclusions that list explicit parameters without a share
code are reported as skipped rather than converted, because that conversion
would require additional, unverified assumptions (e.g. ``color=blue``).

tracker.gg is intentionally NOT supported: its terms of service prohibit
crawling/scraping and it blocks automated requests.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import quote

from app.data.models import ImportMethod
from app.scraper.parsers import extract_templates
from app.scraper.scraper_base import (
    CancelCheck,
    FetchResult,
    PoliteHttpClient,
    ProgressCallback,
    ScrapeCancelled,
    ScraperError,
    SourceAdapter,
    SourceRecord,
)
from app.utils.logging import get_logger

log = get_logger("scraper.liquipedia")

LIQUIPEDIA_API = "https://liquipedia.net/valorant/api.php"
LIQUIPEDIA_PAGE = "https://liquipedia.net/valorant/index.php"
LIQUIPEDIA_SOURCE_NAME = "Liquipedia VALORANT Wiki"
LIQUIPEDIA_LICENSE = "CC-BY-SA 3.0"
LIQUIPEDIA_MIN_INTERVAL_S = 2.5
LIQUIPEDIA_CACHE_TTL_S = 7 * 24 * 3600
TEMPLATE_TITLES = ("Template:CrosshairTable", "Template:Crosshair table")
MAIN_NAMESPACE = 0
TITLES_PER_REQUEST = 50


class LiquipediaCrosshairAdapter(SourceAdapter):
    name = LIQUIPEDIA_SOURCE_NAME

    def __init__(self, client: PoliteHttpClient) -> None:
        self.client = client

    def fetch(
        self,
        progress: ProgressCallback | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> FetchResult:
        report = progress or (lambda _msg: None)
        cancelled = should_cancel or (lambda: False)
        result = FetchResult()

        titles: set[str] = set()
        for template in TEMPLATE_TITLES:
            self._check_cancel(cancelled)
            found = self._embedded_in(template, cancelled)
            report(f"{template}: {len(found)} article pages")
            titles.update(found)

        ordered = sorted(titles)
        for start in range(0, len(ordered), TITLES_PER_REQUEST):
            self._check_cancel(cancelled)
            batch = ordered[start:start + TITLES_PER_REQUEST]
            report(f"Reading pages {start + 1}–{start + len(batch)} of {len(ordered)}")
            for page in self._page_revisions(batch):
                self._records_from_page(page, result)

        result.requests_made = self.client.requests_made
        result.cache_hits = self.client.cache_hits
        report(
            f"Done: {len(result.records)} share codes, {len(result.skipped)} skipped, "
            f"{result.requests_made} requests, {result.cache_hits} cached responses."
        )
        log.info("liquipedia_fetch records=%s skipped=%s requests=%s cache_hits=%s",
                 len(result.records), len(result.skipped), result.requests_made, result.cache_hits)
        return result

    # ------------------------------------------------------------------ API
    def _embedded_in(self, template: str, cancelled: CancelCheck) -> list[str]:
        titles: list[str] = []
        params: dict[str, object] = {
            "action": "query", "list": "embeddedin", "eititle": template,
            "einamespace": MAIN_NAMESPACE, "eilimit": 500, "format": "json",
        }
        while True:
            data = self._query(params)
            titles += [p["title"] for p in data.get("query", {}).get("embeddedin", [])]
            cont = data.get("continue")
            if not cont:
                return titles
            self._check_cancel(cancelled)
            params = {**params, **cont}

    def _page_revisions(self, titles: Iterable[str]) -> list[dict]:
        data = self._query({
            "action": "query", "prop": "revisions", "rvprop": "content|ids|timestamp",
            "rvslots": "main", "titles": "|".join(titles), "format": "json",
            "formatversion": 2,
        })
        return data.get("query", {}).get("pages", [])

    def _query(self, params: dict[str, object]) -> dict:
        data = self.client.get_json(LIQUIPEDIA_API, params)
        if not isinstance(data, dict):
            raise ScraperError("Unexpected API response format.")
        if "error" in data:
            raise ScraperError(f"Liquipedia API error: {data['error']}")
        return data

    # -------------------------------------------------------------- parsing
    def _records_from_page(self, page: dict, result: FetchResult) -> None:
        title = page.get("title", "?")
        revisions = page.get("revisions") or []
        if page.get("missing") or not revisions:
            result.skipped.append(f"{title}: page missing or has no revisions")
            return
        revision = revisions[0]
        content = revision.get("slots", {}).get("main", {}).get("content", "")
        revid = revision.get("revid")
        permalink = f"{LIQUIPEDIA_PAGE}?title={quote(title.replace(' ', '_'))}&oldid={revid}"
        tables = extract_templates(content, {"CrosshairTable", "Crosshair table"})
        if not tables:
            result.skipped.append(f"{title}: no crosshair template found in wikitext")
        for params in tables:
            code = params.get("sharecode", "").strip()
            if not code:
                result.skipped.append(
                    f"{title}: crosshair table without share code (explicit parameters not imported)"
                )
                continue
            result.records.append(
                SourceRecord(
                    code=code,
                    source_name=LIQUIPEDIA_SOURCE_NAME,
                    import_method=ImportMethod.SCRAPER,
                    source_url=permalink,
                    source_player=title,
                    source_date=params.get("date") or None,
                    extra={
                        "ref": params.get("ref", ""),
                        "page_title": title,
                        "revision_id": revid,
                        "revision_timestamp": revision.get("timestamp"),
                        "license": LIQUIPEDIA_LICENSE,
                        "attribution": f"Liquipedia VALORANT Wiki, \"{title}\", {permalink}",
                    },
                )
            )

    @staticmethod
    def _check_cancel(cancelled: CancelCheck) -> None:
        if cancelled():
            raise ScrapeCancelled("Update cancelled by user.")
