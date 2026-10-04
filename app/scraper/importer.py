"""Import pipeline: source records -> parser -> mapping/validation -> crosshair database.

Manual lists and source adapters both produce ``SourceRecord`` objects and go
through the same path. The importer only stores candidate data with
provenance; it never decides a recommendation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from app.crosshair.mapping import Fidelity, map_valorant_profile
from app.data.models import CrosshairRole, CrosshairSource, ImportMethod
from app.data.repository import Repository
from app.scraper.parsers import CrosshairCodeError, parse_valorant_code, resolve_primary
from app.scraper.scraper_base import SourceRecord
from app.utils.logging import get_logger

log = get_logger("scraper.importer")

VALORANT_FORMAT = "valorant_share_code"
CODE_FIELD = re.compile(r"^\d+;")
FIELD_SEPARATOR = re.compile(r"\t|,")


class ImportStatus(StrEnum):
    IMPORTED = "imported"
    SOURCE_ONLY = "source_only"  # provenance stored, no research-model crosshair
    DUPLICATE = "duplicate"
    INVALID = "invalid"


@dataclass
class ImportOutcome:
    line_number: int
    code: str
    status: ImportStatus
    fidelity: Fidelity | None = None
    source_id: int | None = None
    crosshair_id: int | None = None
    player: str | None = None
    messages: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Provenance:
    source_name: str
    import_method: ImportMethod = ImportMethod.MANUAL
    source_url: str | None = None
    source_player: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class ManualLine:
    code: str
    player: str | None = None
    url: str | None = None


def parse_manual_line(line: str) -> ManualLine | None:
    """Parse one manual-entry line. Returns None for blank lines and ``#`` comments.

    Accepted forms (tab- or comma-separated, any order after the player):
        <code>
        <player>, <code>
        <player>, <code>, <url>
    A share code never contains commas or tabs, so it is identified as the
    field starting with ``<digits>;``.
    """
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    fields = [f.strip() for f in FIELD_SEPARATOR.split(text) if f.strip()]
    codes = [f for f in fields if CODE_FIELD.match(f)]
    if len(codes) != 1:
        return ManualLine(code=text)
    urls = [f for f in fields if f.lower().startswith(("http://", "https://"))]
    others = [f for f in fields if f not in codes and f not in urls]
    return ManualLine(code=codes[0], player=others[0] if others else None,
                      url=urls[0] if urls else None)


def import_valorant_codes(
    repo: Repository,
    lines: Iterable[str],
    provenance: Provenance,
    ranges: Mapping[str, tuple[float, float]],
) -> list[ImportOutcome]:
    """Import manually entered lines (see ``parse_manual_line``)."""
    outcomes: list[ImportOutcome] = []
    for line_number, line in enumerate(lines, start=1):
        parsed = parse_manual_line(line)
        if parsed is None:
            continue
        record = SourceRecord(
            code=parsed.code,
            source_name=provenance.source_name,
            import_method=provenance.import_method,
            source_url=parsed.url or provenance.source_url,
            source_player=parsed.player or provenance.source_player,
        )
        outcomes.append(_import_one(repo, line_number, record, ranges, provenance.notes))
    _log_summary(provenance.source_name, outcomes)
    return outcomes


def import_records(
    repo: Repository,
    records: Iterable[SourceRecord],
    ranges: Mapping[str, tuple[float, float]],
    notes: str | None = None,
) -> list[ImportOutcome]:
    """Import records produced by a source adapter."""
    outcomes = [
        _import_one(repo, number, record, ranges, notes)
        for number, record in enumerate(records, start=1)
    ]
    _log_summary("adapter", outcomes)
    return outcomes


def summarize(outcomes: Iterable[ImportOutcome]) -> dict[ImportStatus, int]:
    items = list(outcomes)
    return {status: sum(o.status == status for o in items) for status in ImportStatus}


def _log_summary(source: str, outcomes: list[ImportOutcome]) -> None:
    log.info("valorant_import source=%s summary=%s", source,
             {str(k): v for k, v in summarize(outcomes).items()})


def _import_one(
    repo: Repository,
    number: int,
    record: SourceRecord,
    ranges: Mapping[str, tuple[float, float]],
    notes: str | None,
) -> ImportOutcome:
    player = record.source_player
    try:
        parsed = parse_valorant_code(record.code)
        profile = resolve_primary(parsed)
    except CrosshairCodeError as exc:
        log.warning("valorant_code_invalid item=%s player=%s error=%s", number, player, exc)
        return ImportOutcome(number, record.code, ImportStatus.INVALID, player=player,
                             messages=[str(exc)])

    if repo.find_source(VALORANT_FORMAT, parsed.raw, record.source_name, player):
        return ImportOutcome(
            number, record.code, ImportStatus.DUPLICATE, player=player,
            messages=["Identical code from the same source and player is already stored."],
        )

    mapping = map_valorant_profile(parsed, profile)
    if mapping.config is not None:
        problems = mapping.config.errors(ranges)
        if problems:
            mapping.differences += [f"Outside research parameter ranges: {p}" for p in problems]
            mapping.config = None
            mapping.fidelity = Fidelity.NOT_REPRESENTABLE
    config = mapping.config
    messages = parsed.warnings + profile.warnings + mapping.differences

    source = CrosshairSource(
        source_name=record.source_name,
        import_method=record.import_method,
        source_url=record.source_url,
        source_player=player,
        source_format=VALORANT_FORMAT,
        source_code=parsed.raw,
        notes=notes,
        raw_payload={
            "source_record": {"source_date": record.source_date, "extra": dict(record.extra)},
            "parsed": parsed.to_payload(),
            "resolved_primary": profile.values,
            "resolved_color": {"hex": profile.color_hex, "label": profile.color_label},
            "resolve_warnings": profile.warnings,
            "mapping": mapping.to_payload(),
        },
    )
    crosshair = None
    if config is not None:
        label = player or f"{record.source_name} #{number}"
        crosshair = config.to_record(
            name=f"{label} (VALORANT)",
            role=CrosshairRole.CANDIDATE,
            fidelity=str(mapping.fidelity),
        )
    source, crosshair = repo.add_source_with_crosshair(source, crosshair)
    return ImportOutcome(
        line_number=number,
        code=record.code,
        status=ImportStatus.IMPORTED if crosshair else ImportStatus.SOURCE_ONLY,
        fidelity=mapping.fidelity,
        source_id=source.source_id,
        crosshair_id=crosshair.crosshair_id if crosshair else None,
        player=player,
        messages=messages,
    )
