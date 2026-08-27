"""TaxisTo route-data cleaning pipeline.

Implements the seven cleaning steps described in CLAUDE.md for
`data/cpt/Taxi_Routes.geojson`. Driven by `scripts/clean_routes.py`.

Deliberately pure standard library. CLAUDE.md's "pandas + shapely + networkx"
convention describes the routing engine that consumes this data; none of the
three are needed to sum haversine distances or take a median, and none are
installed in this environment. A pipeline that runs with zero `pip install` is
worth more here than convention compliance.
"""

__version__ = "1.0.0"
