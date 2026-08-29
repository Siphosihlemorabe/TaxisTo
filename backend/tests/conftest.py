import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
# `backend` and `pipeline` are both top-level packages at the repo root.
sys.path.insert(0, str(ROOT))

from backend.app.main import create_app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    # raise_server_exceptions=False so handled NotImplementedError surfaces as
    # the 501 the app is meant to return, instead of propagating into the test.
    return TestClient(create_app(), raise_server_exceptions=False)
