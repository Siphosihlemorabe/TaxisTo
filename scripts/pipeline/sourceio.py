"""Reading the source file and writing artifacts.

Two invariants live here, and the rest of the pipeline depends on both:

1. **`data/` is input only.** `write_json` refuses any path that resolves under
   the source directory. The previous normalisation script read and overwrote
   its own source, which left no way to re-run from pristine input.

2. **Derived fields never round-trip.** The source file (and git history) still
   carries `canonical_origin` and friends from that in-place run. They are
   outputs, so they are stripped at read time regardless of what the file
   contains -- otherwise a bug that read last run's values would confirm itself.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ROOT, PipelineConfig

DATA_DIR = ROOT / "data"

#: Anything a pipeline step produces. Never readable as input.
DERIVED_PREFIXES = ("canonical_", "via_", "measured_")
DERIVED_EXACT = ("canonical", "variants", "issues", "issue_details")

TIER1_FIELDS = ("OBJECTID", "ORGN", "DSTN", "Shape__Length")


class SourceContaminationError(Exception):
    """A derived field reached the transform layer. Always a bug, never data."""


@dataclass
class SourceData:
    features: list[dict]
    sha256: str
    path: Path
    crs: dict | None
    name: str | None
    stripped_keys: list[str] = field(default_factory=list)
    stripped_feature_count: int = 0

    @property
    def contaminated(self) -> bool:
        return bool(self.stripped_keys)


def _is_derived(key: str) -> bool:
    return key in DERIVED_EXACT or key.startswith(DERIVED_PREFIXES)


def load_source(pcfg: PipelineConfig) -> SourceData:
    """Read the route file, stripping any derived properties it carries."""
    raw = pcfg.source_path.read_bytes()
    data = json.loads(raw.decode("utf-8"))

    deny = set(pcfg.ignore_properties)
    stripped: set[str] = set()
    touched = 0

    features = data.get("features") or []
    for f in features:
        props = f.get("properties") or {}
        bad = [k for k in props if k in deny or _is_derived(k)]
        if bad:
            touched += 1
            for k in bad:
                stripped.add(k)
                del props[k]
        f["properties"] = props

    # belt and braces: nothing derived may survive into the transform layer
    for f in features:
        for k in f.get("properties", {}):
            if _is_derived(k):
                raise SourceContaminationError(
                    f"derived property {k!r} survived the load-time strip")

    return SourceData(
        features=features,
        sha256=hashlib.sha256(raw).hexdigest(),
        path=pcfg.source_path,
        crs=data.get("crs"),
        name=data.get("name"),
        stripped_keys=sorted(stripped),
        stripped_feature_count=touched,
    )


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------

def _guard(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(DATA_DIR.resolve())
    except ValueError:
        return resolved
    raise ValueError(f"refusing to write under data/: {path} -- source files are "
                     f"input only")


def write_json(path: Path, obj: Any, *, compact: bool = False) -> str:
    """Write JSON atomically and return its sha256.

    Written to a sibling `.tmp` then moved into place, so a crashed run never
    leaves a half-written audit file behind. Keys are sorted so artifacts are
    byte-identical between runs on identical input.
    """
    path = _guard(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    else:
        text = json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def feature_collection(features: list[dict], src: SourceData, name: str) -> dict:
    """Wrap features in a FeatureCollection carrying the source's CRS."""
    fc: dict = {"type": "FeatureCollection", "name": name}
    if src.crs:
        fc["crs"] = src.crs
    fc["features"] = features
    return fc
