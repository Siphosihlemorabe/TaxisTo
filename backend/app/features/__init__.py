"""Feature packages.

One directory per feature, each self-contained: `router.py` (HTTP surface),
`schemas.py` (wire contracts), `service.py` (logic), and `repository.py` where
the feature owns state the pipeline does not.

The rule that keeps this honest: a feature may import from `app.core`, but
never from another feature. Anything two features both need belongs in `core`.
Cross-feature calls go through a service passed in as a dependency, so the
direction of the dependency stays visible in the signature.
"""
