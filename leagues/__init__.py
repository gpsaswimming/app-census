"""League profiles — the config contract passed into swimparse at ingest time.

A profile (``gpsa.yaml``) carries the age-up date, age-group bands, and scoring
point values a league defines for itself. Its keys mirror the swimparse profile
shape exactly, so a loaded profile can be handed straight to
``swimparse --league-file`` with no remapping.
"""

from __future__ import annotations

from functools import lru_cache
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


@lru_cache(maxsize=None)
def team_alias_map(name: str = "gpsa") -> dict[str, str]:
    """Map every known team code + alias (upper-cased) → its canonical code.

    Built from the profile's ``teams`` registry — the same map swimparse's
    ``applyLeague`` uses to canonicalize codes at parse time. Reusing it here lets
    reference-data importers (divisions) accept drifting/legacy codes and resolve
    them to the canonical code the ingest pipeline stores.
    """
    mapping: dict[str, str] = {}
    for entry in load_profile(name).get("teams", []):
        code = entry["code"]
        mapping[code.upper()] = code
        for alias in entry.get("aliases", []):
            mapping[alias.upper()] = code
    return mapping


def canonical_team_code(code: str, name: str = "gpsa") -> str:
    """Return the canonical league code for a (possibly drifting) team code.

    Unknown codes are returned unchanged (upper-cased passthrough is not forced;
    the raw value is preserved so an unrecognized team surfaces as-is).
    """
    if not code:
        return code
    return team_alias_map(name).get(code.upper(), code)
