"""The parse boundary produces DOB-free, scored meets."""

from __future__ import annotations

import json
import re

from conftest import needs_swimparse

from ingest.swimparse_runner import parse_bytes

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@needs_swimparse
def test_parse_is_dob_free_and_scored(raw_sd3):
    meet = parse_bytes(raw_sd3, "gg-at-ww.sd3")

    assert meet["format"] == "sdif-v3"
    assert meet["ageProfile"] == "gpsa"

    # No birthdate survives, including inside swimmer identity keys.
    assert '"birthDate"' not in json.dumps(meet)
    for s in meet["swimmers"]:
        assert s.get("ageGroup")
        assert not _ISO_DATE.search(s["id"]), f"DOB leaked in id: {s['id']}"

    # --score filled points for both formats: known golden totals.
    scores: dict[str, float] = {}
    for ev in meet["events"]:
        for r in ev["results"]:
            scores[r["teamCode"]] = scores.get(r["teamCode"], 0) + (r.get("points") or 0)
    assert scores == {"GG": 320, "WW": 146}
