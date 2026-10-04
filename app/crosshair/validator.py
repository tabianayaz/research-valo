"""Validation of research-model crosshair parameters."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Any

HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
NUMERIC_FIELDS = ("size", "thickness", "gap", "outline_thickness", "opacity")


def normalize_hex_color(value: Any) -> str | None:
    """Return ``#RRGGBB`` (upper-case) or None if the value is not a valid colour."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.startswith("#"):
        text = "#" + text
    if not HEX_COLOR_PATTERN.fullmatch(text):
        return None
    return text.upper()


def validate_crosshair_values(
    values: Mapping[str, Any], ranges: Mapping[str, tuple[float, float]]
) -> list[str]:
    """Return a list of human-readable problems (empty list means valid)."""
    errors: list[str] = []
    if normalize_hex_color(values.get("color")) is None:
        errors.append(f"color must be a hex colour like #RRGGBB (got {values.get('color')!r}).")

    for name in NUMERIC_FIELDS:
        value = values.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{name} must be a number (got {value!r}).")
            continue
        if not math.isfinite(value):
            errors.append(f"{name} must be finite (got {value!r}).")
            continue
        if name in ranges:
            low, high = ranges[name]
            if not (low <= value <= high):
                errors.append(f"{name} must be between {low:g} and {high:g} (got {value:g}).")

    if not isinstance(values.get("outline_enabled"), bool):
        errors.append(
            f"outline_enabled must be true or false (got {values.get('outline_enabled')!r})."
        )
    return errors
