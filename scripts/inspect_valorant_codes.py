"""Print how each VALORANT code in a file parses and maps (no database writes).

Usage: python scripts/inspect_valorant_codes.py <codes.txt>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crosshair.mapping import map_valorant_profile  # noqa: E402
from app.scraper.parsers import CrosshairCodeError, parse_valorant_code, resolve_primary  # noqa: E402


def main() -> int:
    path = Path(sys.argv[1])
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        code = line.strip()
        if not code or code.startswith("#"):
            continue
        try:
            parsed = parse_valorant_code(code)
            profile = resolve_primary(parsed)
        except CrosshairCodeError as exc:
            print(f"line {number}: INVALID - {exc}")
            continue
        result = map_valorant_profile(parsed, profile)
        print(f"line {number}: {result.fidelity}  color={profile.color_hex} ({profile.color_label})")
        if result.config:
            c = result.config
            print(f"    config: size={c.size:g} thickness={c.thickness:g} gap={c.gap:g} "
                  f"outline={c.outline_enabled}/{c.outline_thickness:g} opacity={c.opacity:g}")
        for message in parsed.warnings + profile.warnings + result.differences:
            print(f"    - {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
