"""Import VALORANT share codes from a text file into the research database.

Usage:
    python scripts/import_valorant_codes.py <codes.txt> --source-name "..." [--source-url URL]
                                            [--player NAME] [--db PATH]

Re-running is safe: identical codes from the same source/player are skipped.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.research import load_research_parameters  # noqa: E402
from app.config.settings import load_settings  # noqa: E402
from app.data.database import Database  # noqa: E402
from app.data.repository import Repository  # noqa: E402
from app.scraper.importer import Provenance, import_valorant_codes  # noqa: E402
from app.utils.logging import configure_logging  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codes_file", type=Path)
    parser.add_argument("--source-name", required=True)
    parser.add_argument("--source-url")
    parser.add_argument("--player")
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()

    settings = load_settings(db_path=args.db)
    settings.ensure_directories()
    configure_logging(settings.logs_dir)
    research = load_research_parameters()
    provenance = Provenance(args.source_name, source_url=args.source_url, source_player=args.player)

    with Database(settings.db_path) as db:
        outcomes = import_valorant_codes(
            Repository(db),
            args.codes_file.read_text(encoding="utf-8").splitlines(),
            provenance,
            research.parameter_ranges,
        )
    for o in outcomes:
        fidelity = f" [{o.fidelity}]" if o.fidelity else ""
        print(f"line {o.line_number}: {o.status}{fidelity}")
        for message in o.messages:
            print(f"    - {message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
