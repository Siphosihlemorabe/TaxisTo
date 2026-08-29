import sys
from pathlib import Path

# <ROOT>/pipeline/tests/conftest.py -> three levels up. `pipeline` and
# `backend` are both top-level packages at the repo root.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
