"""Validate the league profile contract.

Two guarantees:
  1. ``leagues/gpsa.yaml`` has the shape swimparse expects (required keys/types).
  2. It does not DRIFT from swimparse's reference profile
     (``app-tools/swimparse/leagues/gpsa.json``). When that repo is checked out
     alongside this one, the two must be byte-for-value identical — the YAML is
     the editable source of truth, swimparse ships the same values as a built-in.
     When swimparse isn't present (isolated CI), the drift check is skipped and
     only the standalone shape check runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from leagues import load_profile

# app-census and app-tools sit side by side under the GPSA workspace.
_SWIMPARSE_JSON = (
    Path(__file__).resolve().parents[2] / "app-tools" / "swimparse" / "leagues" / "gpsa.json"
)


def test_gpsa_profile_has_expected_shape():
    p = load_profile("gpsa")

    assert p["id"] == "gpsa", "profile id must be season-stable 'gpsa' (no year)"
    assert p["ageUp"]["reference"] == "06-01", "GPSA ages as of June 1"

    labels = [b["label"] for b in p["ageGroups"]]
    assert labels == ["6&U", "7-8", "9-10", "11-12", "13-14", "15-18"]
    for band in p["ageGroups"]:
        assert "label" in band
        assert set(band) <= {"label", "min", "max"}

    scoring = p["scoring"]
    assert scoring["individualPlaces"] == [5, 3, 1]
    assert scoring["relayPlaces"] == [7]
    assert scoring["entriesScoredPerTeam"] == 2


@pytest.mark.skipif(
    not _SWIMPARSE_JSON.exists(),
    reason=f"swimparse reference profile not found at {_SWIMPARSE_JSON}",
)
def test_gpsa_profile_matches_swimparse_reference():
    ours = load_profile("gpsa")
    theirs = json.loads(_SWIMPARSE_JSON.read_text(encoding="utf-8"))
    assert ours == theirs, (
        "leagues/gpsa.yaml has drifted from swimparse's gpsa.json — "
        "edit both together"
    )
