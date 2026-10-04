"""Small reusable validation helpers."""

from __future__ import annotations

import re

PLAYER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{2,32}$")


class ValidationError(ValueError):
    """Raised when user- or source-provided data fails validation."""


def validate_player_id(player_id: str) -> str:
    """Anonymous player IDs: 2-32 chars of letters, digits, '_' or '-'."""
    value = player_id.strip()
    if not PLAYER_ID_PATTERN.fullmatch(value):
        raise ValidationError(
            "Player ID must be 2-32 characters using only letters, digits, '_' or '-'."
        )
    return value


def require_positive(name: str, value: float | int) -> None:
    if value is None or value <= 0:
        raise ValidationError(f"{name} must be greater than 0 (got {value!r}).")


def require_in_range(name: str, value: float, low: float, high: float) -> None:
    if not (low <= value <= high):
        raise ValidationError(f"{name} must be between {low} and {high} (got {value!r}).")
