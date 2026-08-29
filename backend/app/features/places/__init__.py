"""Canonical place gazetteer and name provenance.

Serves the canonical places and their normalisation traces -- including
`explain`, so a reviewer can check a merge over HTTP as well as over the CLI.
"""

from .router import router

__all__ = ["router"]
