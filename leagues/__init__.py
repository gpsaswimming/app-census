"""League profiles — the config contract passed into swimparse at ingest time.

A profile (``gpsa.yaml``) carries the age-up date, age-group bands, and scoring
point values a league defines for itself. Its keys mirror the swimparse profile
shape exactly, so a loaded profile can be handed straight to
``swimparse --league-file`` with no remapping.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_LEAGUES_DIR = Path(__file__).resolve().parent


def load_profile(name: str = "gpsa") -> dict:
    """Load a league profile by name (e.g. ``"gpsa"`` → ``leagues/gpsa.yaml``).

    Returns the profile as a plain dict, ready to serialize to the JSON shape
    swimparse consumes.
    """
    path = _LEAGUES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no league profile {name!r} at {path}")
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)
