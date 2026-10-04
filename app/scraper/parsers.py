"""Parsers for external crosshair formats.

VALORANT crosshair share code
-----------------------------
Format: semicolon-separated tokens. The first token is a format version
(``0``). ``P``, ``A`` and ``S`` start the primary, ADS and sniper sections;
tokens before the first section are general profile options. Inside a section
tokens alternate ``key;value``. Keys that are absent take the in-game default.

Key meanings and defaults are taken from community documentation, not from an
official Riot specification:

* Liquipedia VALORANT Wiki, ``Module:Crosshair``
  (https://liquipedia.net/valorant/Module:Crosshair)
* valorant-spind.de, "Valorant Crosshair Checker" key table
  (https://www.valorant-spind.de/en/valorant-crosshair-zwilling.html)

Where the two disagree (meaning of ``0g``/``1g``, outer-line movement error
default) the behaviour observed in real codes was used: ``g=1`` makes the
vertical length independent (``0;P;0l;0;0v;3;0g;1`` is a vertical-only cross),
and codes routinely write ``1m;0``, implying the default is 1.

Only the primary section is resolved into a profile. ADS/sniper sections and
uninterpreted keys are preserved verbatim so nothing is lost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.crosshair.shape import CrosshairShape, Dot, LineSet, Outline
from app.utils.validators import ValidationError

PARSER_VERSION = "valorant-code-1"
SECTION_MARKERS = {"P": "primary", "A": "ads", "S": "sniper"}
KEY_PATTERN = re.compile(r"^[01]?[A-Za-z]$")
HEX_PATTERN = re.compile(r"^[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")

# Preset colours (index -> RGB). Approximate values from Liquipedia Module:Crosshair;
# the exact in-game RGB values are not officially documented.
PRESET_COLORS: dict[int, tuple[str, str]] = {
    0: ("White", "#FFFFFF"),
    1: ("Green", "#00FF00"),
    2: ("Yellow Green", "#A7FF00"),
    3: ("Green Yellow", "#DFFF00"),
    4: ("Yellow", "#FFFF00"),
    5: ("Cyan", "#00FFFF"),
    6: ("Pink", "#FF6EC7"),
    7: ("Red", "#FB8686"),
}
CUSTOM_COLOR_INDEX = 8


@dataclass(frozen=True)
class KeySpec:
    name: str
    default: float
    low: float
    high: float
    is_bool: bool = False


# Primary-section keys with an interpreted meaning.
PRIMARY_KEYS: dict[str, KeySpec] = {
    "c": KeySpec("color_index", 0, 0, 8),
    "h": KeySpec("outline_enabled", 1, 0, 1, True),
    "t": KeySpec("outline_thickness", 1, 1, 6),
    "o": KeySpec("outline_opacity", 0.5, 0, 1),
    "d": KeySpec("dot_enabled", 0, 0, 1, True),
    "z": KeySpec("dot_size", 2, 1, 6),
    "a": KeySpec("dot_opacity", 1, 0, 1),
    "f": KeySpec("fade_with_firing_error", 1, 0, 1, True),
    "0b": KeySpec("inner_enabled", 1, 0, 1, True),
    "0t": KeySpec("inner_thickness", 2, 0, 10),
    "0l": KeySpec("inner_length", 6, 0, 20),
    "0v": KeySpec("inner_length_vertical", 6, 0, 20),
    "0g": KeySpec("inner_vertical_independent", 0, 0, 1, True),
    "0o": KeySpec("inner_offset", 3, 0, 20),
    "0a": KeySpec("inner_opacity", 0.8, 0, 1),
    "0m": KeySpec("inner_movement_error", 0, 0, 1, True),
    "0f": KeySpec("inner_firing_error", 1, 0, 1, True),
    "0s": KeySpec("inner_movement_error_multiplier", 1, 0, 3),
    "0e": KeySpec("inner_firing_error_multiplier", 1, 0, 3),
    "1b": KeySpec("outer_enabled", 1, 0, 1, True),
    "1t": KeySpec("outer_thickness", 2, 0, 10),
    "1l": KeySpec("outer_length", 2, 0, 20),
    "1v": KeySpec("outer_length_vertical", 2, 0, 20),
    "1g": KeySpec("outer_vertical_independent", 0, 0, 1, True),
    "1o": KeySpec("outer_offset", 10, 0, 40),
    "1a": KeySpec("outer_opacity", 0.35, 0, 1),
    "1m": KeySpec("outer_movement_error", 1, 0, 1, True),
    "1f": KeySpec("outer_firing_error", 1, 0, 1, True),
    "1s": KeySpec("outer_movement_error_multiplier", 1, 0, 3),
    "1e": KeySpec("outer_firing_error_multiplier", 1, 0, 3),
}
# Keys known to appear in primary sections whose exact meaning is not reliably
# documented. They are preserved but not interpreted.
UNINTERPRETED_PRIMARY_KEYS = {"m", "b", "u"}


class CrosshairCodeError(ValidationError):
    """The code cannot be parsed at all."""


@dataclass
class ValorantCode:
    raw: str
    version: str
    general: dict[str, str] = field(default_factory=dict)
    sections: dict[str, dict[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "parser_version": PARSER_VERSION,
            "version": self.version,
            "general": self.general,
            "sections": self.sections,
            "warnings": self.warnings,
        }


@dataclass
class ValorantProfile:
    """Primary crosshair with every interpreted key resolved (defaults applied)."""

    values: dict[str, float]
    color_hex: str
    color_label: str
    explicit_keys: set[str]
    uninterpreted: dict[str, str]
    warnings: list[str]

    def __getattr__(self, name: str) -> Any:
        values = self.__dict__.get("values", {})
        if name in values:
            return values[name]
        raise AttributeError(name)

    def flag(self, name: str) -> bool:
        return bool(self.values[name])

    def inner_vertical_length(self) -> float:
        return self.inner_length_vertical if self.flag("inner_vertical_independent") else self.inner_length

    def outer_vertical_length(self) -> float:
        return self.outer_length_vertical if self.flag("outer_vertical_independent") else self.outer_length

    def to_shape(self) -> CrosshairShape:
        """Static (no movement/firing error) rendering of the original crosshair."""
        line_sets = []
        if self.flag("inner_enabled"):
            line_sets.append(LineSet(self.inner_offset, self.inner_length,
                                     self.inner_vertical_length(), self.inner_thickness,
                                     self.inner_opacity))
        if self.flag("outer_enabled"):
            line_sets.append(LineSet(self.outer_offset, self.outer_length,
                                     self.outer_vertical_length(), self.outer_thickness,
                                     self.outer_opacity))
        dot = Dot(self.dot_size, self.dot_opacity) if self.flag("dot_enabled") else None
        outline = (
            Outline(self.outline_thickness, self.outline_opacity)
            if self.flag("outline_enabled") else None
        )
        return CrosshairShape(self.color_hex, tuple(line_sets), dot, outline)


def parse_valorant_code(code: str) -> ValorantCode:
    """Tokenize a share code into general options and raw per-section key/values."""
    if not isinstance(code, str) or not code.strip():
        raise CrosshairCodeError("Empty crosshair code.")
    text = code.strip()
    tokens = text.split(";")
    if tokens and tokens[-1] == "":
        tokens = tokens[:-1]
    version = tokens[0]
    if not version.isdigit():
        raise CrosshairCodeError(f"Code must start with a numeric version, got {version!r}.")

    result = ValorantCode(raw=text, version=version)
    current: dict[str, str] = result.general
    current_name = "general"
    index = 1
    while index < len(tokens):
        token = tokens[index].strip()
        if token in SECTION_MARKERS:
            current_name = SECTION_MARKERS[token]
            if current_name in result.sections:
                result.warnings.append(f"Section {token} appears more than once; merged.")
            current = result.sections.setdefault(current_name, {})
            index += 1
            continue
        if not KEY_PATTERN.fullmatch(token):
            raise CrosshairCodeError(f"Unexpected token {token!r} at position {index}.")
        value = tokens[index + 1].strip() if index + 1 < len(tokens) else ""
        if value == "" or value in SECTION_MARKERS:
            result.warnings.append(
                f"Key {token!r} in {current_name} has no value; the default is used."
            )
            index += 1 if value in SECTION_MARKERS else 2
            continue
        if token in current:
            result.warnings.append(f"Key {token!r} repeated in {current_name}; last value kept.")
        current[token] = value
        index += 2

    if "primary" not in result.sections:
        raise CrosshairCodeError("Code has no primary (P) section.")
    return result


def resolve_primary(code: ValorantCode) -> ValorantProfile:
    raw = code.sections["primary"]
    warnings: list[str] = []
    values: dict[str, float] = {}
    for key, spec in PRIMARY_KEYS.items():
        if key not in raw:
            values[spec.name] = spec.default
            continue
        try:
            number = float(raw[key])
        except ValueError:
            warnings.append(f"Key {key!r} has non-numeric value {raw[key]!r}; default used.")
            values[spec.name] = spec.default
            continue
        clamped = min(max(number, spec.low), spec.high)
        if clamped != number:
            warnings.append(f"Key {key!r}={number:g} outside [{spec.low:g}, {spec.high:g}]; clamped.")
        values[spec.name] = float(bool(clamped)) if spec.is_bool else clamped

    uninterpreted = {k: v for k, v in raw.items() if k in UNINTERPRETED_PRIMARY_KEYS and k != "u"}
    unknown = {k: v for k, v in raw.items() if k not in PRIMARY_KEYS and k not in UNINTERPRETED_PRIMARY_KEYS}
    if unknown:
        warnings.append(f"Unknown keys preserved but not interpreted: {sorted(unknown)}.")
        uninterpreted.update(unknown)

    color_hex, color_label = _resolve_color(int(values["color_index"]), raw.get("u"), warnings)
    return ValorantProfile(
        values=values,
        color_hex=color_hex,
        color_label=color_label,
        explicit_keys=set(raw),
        uninterpreted=uninterpreted,
        warnings=warnings,
    )


def extract_templates(wikitext: str, names: set[str]) -> list[dict[str, str]]:
    """Return the named parameters of every ``{{Name|...}}`` transclusion in ``wikitext``.

    Template names are matched case-insensitively with spaces/underscores
    treated alike (MediaWiki semantics). Nested templates and links inside
    parameter values are kept verbatim; ``|`` inside them does not split.
    """
    wanted = {_normalize_template_name(n) for n in names}
    results: list[dict[str, str]] = []
    index = 0
    while True:
        start = wikitext.find("{{", index)
        if start < 0:
            return results
        end = _matching_close(wikitext, start)
        if end < 0:
            return results
        body = wikitext[start + 2:end]
        parts = _split_top_level(body)
        if parts and _normalize_template_name(parts[0]) in wanted:
            params: dict[str, str] = {}
            for part in parts[1:]:
                key, sep, value = part.partition("=")
                if sep:
                    params[key.strip().lower()] = value.strip()
            results.append(params)
            index = end + 2
        else:
            index = start + 2


def _normalize_template_name(name: str) -> str:
    return name.strip().replace("_", " ").lower().removeprefix("template:")


def _matching_close(text: str, start: int) -> int:
    depth = 0
    i = start
    while i < len(text) - 1:
        pair = text[i:i + 2]
        if pair == "{{":
            depth += 1
            i += 2
        elif pair == "}}":
            depth -= 1
            if depth == 0:
                return i
            i += 2
        else:
            i += 1
    return -1


def _split_top_level(body: str) -> list[str]:
    parts: list[str] = []
    depth_braces = depth_links = 0
    current: list[str] = []
    i = 0
    while i < len(body):
        pair = body[i:i + 2]
        if pair in ("{{", "[[", "}}", "]]"):
            if pair == "{{":
                depth_braces += 1
            elif pair == "}}":
                depth_braces -= 1
            elif pair == "[[":
                depth_links += 1
            else:
                depth_links -= 1
            current.append(pair)
            i += 2
            continue
        char = body[i]
        if char == "|" and depth_braces == 0 and depth_links == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        i += 1
    parts.append("".join(current))
    return parts


def _resolve_color(index: int, custom: str | None, warnings: list[str]) -> tuple[str, str]:
    if index == CUSTOM_COLOR_INDEX:
        if custom and HEX_PATTERN.fullmatch(custom):
            if len(custom) == 8 and custom[6:].upper() != "FF":
                warnings.append(f"Custom colour alpha {custom[6:]} ignored (colour treated as opaque).")
            return "#" + custom[:6].upper(), "Custom"
        warnings.append(f"Custom colour selected but value {custom!r} is invalid; white used.")
        return PRESET_COLORS[0][1], "Custom (invalid, white used)"
    if custom is not None:
        warnings.append("Custom colour value present but colour index is not 8; preset used.")
    label, hex_value = PRESET_COLORS.get(index, PRESET_COLORS[0])
    return hex_value, label
