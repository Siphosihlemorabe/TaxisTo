"""Cross-cutting infrastructure: settings, dependencies, errors, pipeline access.

Nothing here is feature logic. Features may import from `core`; `core` must
never import from `features`.
"""
