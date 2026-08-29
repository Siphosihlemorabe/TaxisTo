"""Tests for the scaffold itself.

These assert the structure holds -- that every feature is mounted, that
unimplemented endpoints say so rather than returning empty results, and that
the pipeline coupling is real. They do not test feature logic, because there
isn't any yet.
"""

import pytest

from backend.app.api import api_router
from backend.app.main import API_PREFIX


class TestSystem:
    def test_health_is_live(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_health_is_mounted_both_versioned_and_not(self, client):
        assert client.get("/health").status_code == 200
        assert client.get(f"{API_PREFIX}/health").status_code == 200

    def test_ready_reports_the_data_it_is_serving(self, client):
        """Provenance must describe the cleaning run, not the installed code."""
        body = client.get("/ready").json()
        assert body["ready"] is True
        assert body["data_source"] == "artifacts"
        p = body["provenance"]
        assert p["backend"] == "artifacts"
        assert p["source_file"], "should name the file that was cleaned"
        assert p["source_sha256"], "should pin the exact input"
        assert p["generated_at"], "should say when the run happened"
        assert p["pipeline_config_sha256"] and p["place_config_sha256"]


class TestScaffoldIsHonest:
    """An unimplemented endpoint must be distinguishable from a working one."""

    @pytest.mark.parametrize("method,path,kwargs", [
        ("post", "/routes/search",
         {"json": {"origin": "GUGULETHU", "destination": "CAPE TOWN"}}),
        ("get", "/routes/pair", {"params": {"origin": "A", "destination": "B"}}),
        ("get", "/routes/1", {}),
        ("get", "/places/search", {"params": {"q": "GUGU"}}),
        ("get", "/places/explain", {"params": {"name": "GUGULETU"}}),
        ("get", "/places/ATLANTIS", {}),
        ("get", "/fares", {"params": {"origin": "A", "destination": "B"}}),
        ("post", "/fares/reports",
         {"json": {"origin": "A", "destination": "B", "amount_zar": "25.00"}}),
        ("post", "/pickup/requests",
         {"json": {"location": {"lon": 18.4, "lat": -33.9}, "destination": "B"}}),
        ("get", "/pickup/requests", {"params": {"lon": 18.4, "lat": -33.9}}),
        ("delete", "/pickup/requests/abc", {}),
        ("post", "/whatsapp/webhook", {"data": {"Body": "hi"}}),
    ])
    def test_stub_returns_501_not_empty_success(self, client, method, path, kwargs):
        r = getattr(client, method)(f"{API_PREFIX}{path}", **kwargs)
        assert r.status_code == 501, f"{method.upper()} {path} -> {r.status_code}"
        assert r.json()["error"]["code"] == "not_implemented"

    def test_501_body_names_what_is_missing(self, client):
        r = client.post(f"{API_PREFIX}/routes/search",
                        json={"origin": "A", "destination": "B"})
        assert "Needs:" in r.json()["error"]["message"]


class TestValidationStillRuns:
    """Stubs must not swallow bad input -- 422 has to beat 501."""

    def test_missing_field_is_422(self, client):
        r = client.post(f"{API_PREFIX}/routes/search", json={"origin": "A"})
        assert r.status_code == 422

    def test_out_of_range_coordinate_is_422(self, client):
        r = client.get(f"{API_PREFIX}/pickup/requests",
                       params={"lon": 999, "lat": -33.9})
        assert r.status_code == 422


class TestFeatureIsolation:
    def test_every_feature_is_mounted(self, client):
        prefixes = {r.path.split("/")[1] for r in api_router.routes}
        assert prefixes >= {"routes", "places", "fares", "pickup", "whatsapp"}

    def test_no_feature_imports_another_feature(self):
        """The rule in app/features/__init__.py, enforced rather than documented."""
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1] / "app" / "features"
        offenders = []
        for path in root.rglob("*.py"):
            own = path.relative_to(root).parts[0]
            for line in path.read_text(encoding="utf-8").splitlines():
                m = re.match(r"\s*from backend\.app\.features\.(\w+)", line)
                if m and m.group(1) != own:
                    offenders.append(f"{path.relative_to(root)}: {line.strip()}")
        assert not offenders, "features must not import each other:\n" + "\n".join(offenders)


class TestPipelineIsNotADependency:
    """Cleaning is offline. The backend reads its result and nothing more.

    This is the boundary that lets the data move to PostGIS: anything importing
    `pipeline` would have to be rewritten at that point, so nothing may.
    """

    def test_no_backend_module_imports_pipeline(self):
        import pathlib
        import re

        app_root = pathlib.Path(__file__).resolve().parents[1] / "app"
        offenders = []
        for path in app_root.rglob("*.py"):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.match(r"\s*(from pipeline[\s.]|import pipeline\b)", line):
                    offenders.append(f"{path.relative_to(app_root)}:{n}: {line.strip()}")
        assert not offenders, (
            "the backend must not import the pipeline:\n" + "\n".join(offenders))

    def test_the_interface_is_query_shaped_not_file_shaped(self):
        """A file-shaped method would be unimplementable over SQL."""
        from backend.app.core.datasource import RouteDataSource

        names = {n for n in vars(RouteDataSource) if not n.startswith("_")}
        assert not {"load", "read", "output_dir", "artifact_status"} & names, (
            "RouteDataSource must not expose file concepts; PostGIS cannot honour them")
        assert {"routes_for_pair", "places_near", "provenance"} <= names


class TestDataSourceIsSwappable:
    def test_both_implementations_satisfy_the_interface(self):
        from backend.app.core.datasource import (ArtifactDataSource,
                                                 PostgisDataSource,
                                                 RouteDataSource)

        # Neither is abstract: every method on the interface is implemented.
        assert issubclass(ArtifactDataSource, RouteDataSource)
        assert issubclass(PostgisDataSource, RouteDataSource)
        ArtifactDataSource(output_dir="output")
        PostgisDataSource(dsn="postgresql://localhost/taxisto")

    def test_ready_still_answers_when_the_source_cannot_serve(self):
        """A readiness probe must report not-ready, never error."""
        from fastapi.testclient import TestClient

        from backend.app.core.config import Settings, get_settings
        from backend.app.main import create_app

        app = create_app()
        app.dependency_overrides[get_settings] = lambda: Settings(
            data_source="postgis", postgis_dsn="postgresql://localhost/x")
        c = TestClient(app, raise_server_exceptions=False)
        r = c.get("/ready")
        assert r.status_code == 200, "readiness must answer even when not ready"
        assert r.json()["ready"] is False
        assert r.json()["data_source"] == "postgis"

    def test_postgis_selected_without_a_dsn_is_a_configuration_error(self):
        from backend.app.core.config import DataSourceKind
        from backend.app.core.deps import _build_source
        from backend.app.core.errors import ConfigurationError

        with pytest.raises(ConfigurationError):
            _build_source(DataSourceKind.postgis, __import__("pathlib").Path("."), None)


@pytest.fixture(scope="session")
def source():
    import pathlib

    from backend.app.core.datasource import ArtifactDataSource

    root = pathlib.Path(__file__).resolve().parents[2]
    return ArtifactDataSource(root / "output")


class TestArtifactSource:
    """The one implementation that actually works, checked against real data."""

    def test_reads_routes_and_places(self, source):
        assert source.is_ready()
        assert source.get_place("GUGULETHU") is not None
        assert source.provenance().source_features == 1417

    def test_pair_lookup_is_direction_sensitive(self, source):
        """A->B and B->A are different services; folding them would be wrong."""
        forward = source.routes_for_pair("KHAYELITSHA", "WYNBERG")
        assert forward, "expected a known pair to resolve"
        for r in forward:
            assert (r.canonical_origin, r.canonical_destination) == \
                ("KHAYELITSHA", "WYNBERG")

    def test_pair_results_put_the_canonical_route_first(self, source):
        multi = next((rs for rs in (source.routes_for_pair(o, d)
                                    for o, d in [("KHAYELITSHA", "WYNBERG")])
                      if len(rs) > 1), None)
        if multi:
            assert multi[0].canonical, "step 6's pick must lead the list"

    def test_search_is_deterministic_not_fuzzy(self, source):
        """NORWOOD must never pull in NORTHWOOD -- they are 10.8 km apart."""
        names = {p.canonical_name for p in source.search_places("NORWOOD", limit=20)}
        assert "NORTHWOOD" not in names

    def test_name_traces_stay_structured(self, source):
        """The trace is evidence, not a log line.

        GUGULETU -> GUGULETHU must arrive carrying the reason and the source
        that justify it; flattening the stages to strings would leave the API
        unable to show a reviewer why a merge happened.
        """
        r = source.resolve_name("GUGULETU")
        assert r.canonical == "GUGULETHU" and r.changed
        alias = next(t for t in r.trace if t["stage"] == "alias")
        assert alias["provenance"]["reason"]
        assert alias["provenance"]["source"]

    def test_weak_resolutions_say_so(self, source):
        r = source.resolve_name("3RD STEEN BIG BAY (VIA PAARDEN EILAND)")
        assert r.via == "PAARDEN EILAND", "via metadata must be split out"
        assert "low_support_place" in r.review_codes

    def test_missing_artifacts_raise_503_not_500(self, tmp_path):
        from backend.app.core.datasource import ArtifactDataSource
        from backend.app.core.errors import DataUnavailableError

        empty = ArtifactDataSource(tmp_path)
        assert not empty.is_ready()
        with pytest.raises(DataUnavailableError):
            empty.get_route(1)
