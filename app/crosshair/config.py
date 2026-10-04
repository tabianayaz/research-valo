"""CrosshairConfig: the research crosshair model.

Exactly the parameters defined for this research: color, size, thickness,
gap, outline (enabled + thickness) and opacity. Units are abstract crosshair
units converted to pixels by ``px_per_unit`` (see ``shape.py``).

Interpretation (shared with the renderer):

* ``size``  – length of each of the four arms.
* ``gap``   – distance from the center point to the start of each arm.
* ``thickness`` – arm width.
* ``opacity``   – alpha of the arms.
* Outline is drawn black, ``outline_thickness`` wide, with the *same* opacity as
  the arms (the research model has no separate outline opacity).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from app.crosshair.shape import CrosshairShape, LineSet, Outline
from app.crosshair.validator import normalize_hex_color, validate_crosshair_values
from app.data.models import CrosshairRecord, CrosshairRole
from app.utils.validators import ValidationError

FIELDS = ("color", "size", "thickness", "gap", "outline_enabled", "outline_thickness", "opacity")


@dataclass(frozen=True)
class CrosshairConfig:
    color: str
    size: float
    thickness: float
    gap: float
    outline_enabled: bool
    outline_thickness: float
    opacity: float

    # ------------------------------------------------------------ validation
    def errors(self, ranges: Mapping[str, tuple[float, float]]) -> list[str]:
        return validate_crosshair_values(self.to_dict(), ranges)

    def validated(self, ranges: Mapping[str, tuple[float, float]]) -> "CrosshairConfig":
        problems = self.errors(ranges)
        if problems:
            raise ValidationError("Invalid crosshair: " + " ".join(problems))
        return self

    # --------------------------------------------------------- serialization
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CrosshairConfig":
        """Strict construction: every field must be present with the right type."""
        missing = [f for f in FIELDS if f not in data]
        if missing:
            raise ValidationError(f"Crosshair data is missing fields: {', '.join(missing)}")
        color = normalize_hex_color(data["color"])
        if color is None:
            raise ValidationError(f"Malformed crosshair color {data['color']!r}")
        if not isinstance(data["outline_enabled"], bool):
            raise ValidationError("outline_enabled must be a boolean")
        try:
            numbers = {
                name: float(data[name])
                for name in ("size", "thickness", "gap", "outline_thickness", "opacity")
                if not isinstance(data[name], bool)
            }
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Malformed crosshair value: {exc}") from exc
        if len(numbers) != 5:
            raise ValidationError("Numeric crosshair fields must not be booleans")
        return cls(color=color, outline_enabled=data["outline_enabled"], **numbers)

    @classmethod
    def from_json(cls, text: str) -> "CrosshairConfig":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Malformed crosshair JSON: {exc}") from exc
        return cls.from_dict(data)

    # ------------------------------------------------------------ persistence
    def to_record(
        self,
        name: str,
        role: CrosshairRole,
        source_id: int | None = None,
        fidelity: str | None = None,
    ) -> CrosshairRecord:
        return CrosshairRecord(
            name=name, role=role, source_id=source_id, fidelity=fidelity, **self.to_dict()
        )

    @classmethod
    def from_record(cls, record: CrosshairRecord) -> "CrosshairConfig":
        return cls.from_dict({f: getattr(record, f) for f in FIELDS})

    # ---------------------------------------------------------------- render
    def to_shape(self) -> CrosshairShape:
        return CrosshairShape(
            color=self.color,
            line_sets=(
                LineSet(self.gap, self.size, self.size, self.thickness, self.opacity),
            ),
            outline=Outline(self.outline_thickness, self.opacity) if self.outline_enabled else None,
        )
