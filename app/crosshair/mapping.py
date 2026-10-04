"""Mapping from external crosshair models into the research CrosshairConfig.

The research model is deliberately smaller than VALORANT's crosshair model, so
mapping can lose information. Every mapping returns a fidelity label and the
exact list of differences so the loss is visible, never silent:

* ``exact``             – every visible static element is represented.
* ``approximate``       – a CrosshairConfig was produced, but some visible
                          property differs (listed in ``differences``).
* ``not_representable`` – the visible crosshair cannot be expressed (e.g. a
                          dot-only crosshair); no CrosshairConfig is produced.

Mapping rules (VALORANT primary profile -> CrosshairConfig):

    color             <- resolved colour (preset RGB approximated, see parsers.py)
    size              <- inner line horizontal length (0l)
    gap               <- inner line offset (0o)
    thickness         <- inner line thickness (0t)
    opacity           <- inner line opacity (0a)
    outline_enabled   <- outlines on (h) AND outline opacity (o) > 0
    outline_thickness <- outline thickness (t)

Dynamic behaviour (movement/firing error, fade) is not part of a static
crosshair and is reported as information only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.crosshair.config import CrosshairConfig
from app.scraper.parsers import ValorantCode, ValorantProfile

DEFAULT_OUTLINE_THICKNESS = 1.0


class Fidelity(StrEnum):
    EXACT = "exact"
    APPROXIMATE = "approximate"
    NOT_REPRESENTABLE = "not_representable"


@dataclass
class MappingResult:
    config: CrosshairConfig | None
    fidelity: Fidelity
    differences: list[str] = field(default_factory=list)
    information: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "fidelity": str(self.fidelity),
            "differences": self.differences,
            "information": self.information,
            "config": self.config.to_dict() if self.config else None,
        }


def _inner_visible(p: ValorantProfile) -> bool:
    return (
        p.flag("inner_enabled")
        and p.inner_thickness > 0
        and p.inner_opacity > 0
        and (p.inner_length > 0 or p.inner_vertical_length() > 0)
    )


def _outer_visible(p: ValorantProfile) -> bool:
    return (
        p.flag("outer_enabled")
        and p.outer_thickness > 0
        and p.outer_opacity > 0
        and (p.outer_length > 0 or p.outer_vertical_length() > 0)
    )


def _dot_visible(p: ValorantProfile) -> bool:
    return p.flag("dot_enabled") and p.dot_opacity > 0 and p.dot_size > 0


def map_valorant_profile(code: ValorantCode, profile: ValorantProfile) -> MappingResult:
    differences: list[str] = []
    information: list[str] = []

    if profile.color_label not in ("Custom",):
        information.append(
            f"Preset colour '{profile.color_label}' mapped to approximate RGB {profile.color_hex}."
        )
    for section in ("ads", "sniper"):
        if section in code.sections:
            information.append(f"{section.upper()} section present; only the primary crosshair is used.")
    if code.general:
        information.append(f"General profile options not used: {code.general}.")
    if profile.uninterpreted:
        information.append(f"Uninterpreted keys preserved: {profile.uninterpreted}.")
    dynamic = [
        name for name in ("inner_movement_error", "inner_firing_error",
                          "outer_movement_error", "outer_firing_error")
        if profile.flag(name)
        and (name.startswith("inner") and _inner_visible(profile)
             or name.startswith("outer") and _outer_visible(profile))
    ]
    if dynamic:
        information.append(
            f"Dynamic behaviour not represented (static crosshair): {', '.join(dynamic)}."
        )

    if not _inner_visible(profile):
        visible = [n for n, v in (("center dot", _dot_visible(profile)),
                                  ("outer lines", _outer_visible(profile))) if v]
        reason = ("only " + " and ".join(visible) + " visible") if visible else "nothing visible"
        differences.append(f"No visible inner lines ({reason}); the research model needs inner lines.")
        return MappingResult(None, Fidelity.NOT_REPRESENTABLE, differences, information)

    horizontal = profile.inner_length
    vertical = profile.inner_vertical_length()
    if horizontal <= 0 or vertical <= 0:
        axis = "vertical" if horizontal <= 0 else "horizontal"
        differences.append(
            f"Inner lines are {axis}-only (horizontal {horizontal:g}, vertical {vertical:g}); "
            "the research model always draws four arms."
        )
        return MappingResult(None, Fidelity.NOT_REPRESENTABLE, differences, information)
    if vertical != horizontal:
        differences.append(
            f"Vertical inner length {vertical:g} differs from horizontal {horizontal:g}; "
            f"size uses the horizontal length."
        )
    if _dot_visible(profile):
        differences.append(f"Center dot (size {profile.dot_size:g}, opacity {profile.dot_opacity:g}) dropped.")
    if _outer_visible(profile):
        differences.append(
            f"Outer lines (length {profile.outer_length:g}, offset {profile.outer_offset:g}, "
            f"opacity {profile.outer_opacity:g}) dropped."
        )

    outline_on = profile.flag("outline_enabled") and profile.outline_opacity > 0
    if outline_on and profile.outline_opacity != profile.inner_opacity:
        differences.append(
            f"Outline opacity {profile.outline_opacity:g} differs from line opacity "
            f"{profile.inner_opacity:g}; the research model draws the outline at line opacity."
        )

    config = CrosshairConfig(
        color=profile.color_hex,
        size=float(horizontal),
        thickness=float(profile.inner_thickness),
        gap=float(profile.inner_offset),
        outline_enabled=outline_on,
        outline_thickness=float(profile.outline_thickness if outline_on else DEFAULT_OUTLINE_THICKNESS),
        opacity=float(profile.inner_opacity),
    )
    fidelity = Fidelity.APPROXIMATE if differences else Fidelity.EXACT
    return MappingResult(config, fidelity, differences, information)
