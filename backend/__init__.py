"""TaxisTo backend.

A package, not just a directory, so one `sys.path` entry -- the repo root --
makes it importable alongside the sibling `pipeline` package.

The backend does not import `pipeline`. Cleaning is an offline concern; the API
only reads its result, through `backend/app/core/datasource/`.
"""
