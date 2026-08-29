"""TaxisTo route-data cleaning pipeline.

Implements the seven cleaning steps described in CLAUDE.md for
`data/cpt/Taxi_Routes.geojson`.

    python -m pipeline run          # CLI, see pipeline/cli.py

Importable as a package from anywhere in the repo -- `backend/` depends on it
directly rather than only on the files it writes.

Deliberately pure standard library. CLAUDE.md's "pandas + shapely + networkx"
convention describes the routing engine that consumes this data; none of the
three are needed to sum haversine distances or take a median, and none are
installed in this environment. A pipeline that runs with zero `pip install` is
worth more here than convention compliance. The backend layered on top may add
dependencies of its own -- that constraint stops at this package boundary.
"""

__version__ = "1.1.0"
