"""SUPERSEDED -- use `scripts/clean_routes.py` instead.

This script implemented CLAUDE.md cleaning steps 2 and 3 for Pass 5, and
findings.md cites it by name as the provenance of the settled naming decision.
It is kept for that reference, but it no longer does the work:

  * The alias tables it used to hold as Python dict literals now live in
    `config/place_aliases.json`, where they can be edited, reviewed and
    reverted without touching code.
  * The transforms it defined (`split_via`, `tidy`, `canonical_key`,
    `haversine`, `consensus`) moved to `scripts/pipeline/places.py` and
    `scripts/pipeline/geometry.py` and are re-exported below, so there is one
    implementation rather than two that can drift apart.
  * **Its in-place write path is gone.** It used to read and overwrite
    `data/cpt/Taxi_Routes.geojson`, which left no way to re-run from pristine
    input and put derived fields into the source file and into git history.
    `data/` is now input only.

What to run instead:

    python scripts/clean_routes.py run                  # all seven steps
    python scripts/clean_routes.py explain "GUGULETU"   # why a name changed
    python scripts/clean_routes.py revert --verify      # prove it is lossless
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.geometry import consensus, coords, haversine  # noqa: F401
from pipeline.places import (canonical_key, split_via,  # noqa: F401
                             tidy)

__all__ = ["split_via", "tidy", "canonical_key", "coords", "haversine", "consensus"]


def main() -> int:
    print(__doc__, file=sys.stderr)
    print("This script no longer writes anything. Run:\n"
          "    python scripts/clean_routes.py run", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
