"""Dashboard port guardrails (no DB, no Docker).

Cheap checks that the analytics port stays wired to the new DOB-free schema:
every dashboard module imports cleanly, and none references the retired
gpsa-census schema (``Swimmer``/``league_age``) or the old ``src.*`` layout.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"

_MODULES = [
    "dashboard.app",
    "dashboard.analysis.overview",
    "dashboard.analysis.alignment",
    "dashboard.analysis.team_analytics",
    "dashboard.analysis.division_setup",
    "dashboard.analysis.qt_analysis",
    "dashboard.analysis.qualifying_times",
    "dashboard.analysis.qt_heatmap",
    "dashboard.analysis.qt_sensitivity",
    "dashboard.utils.filters",
    "dashboard.utils.division_config",
]

# Code patterns that must not survive the port. The retired ORM attribute
# ``Result.league_age`` and the ``Swimmer`` model are gone (age-group bands
# replace exact age); imports come from ``db``/``dashboard``, not ``src.*``.
# (Prose mentions of "league_age" in comments explaining the change are fine —
# we ban the attribute access, not the word.)
_BANNED = (
    "Result.league_age",
    ".swimmer_id",
    "src.database",
    "src.analysis",
    "src.utils",
    "import Swimmer",
)


@pytest.mark.parametrize("module", _MODULES)
def test_module_imports(module):
    pytest.importorskip("streamlit")
    pytest.importorskip("pandas")
    importlib.import_module(module)


def test_no_retired_schema_tokens():
    for path in _DASHBOARD.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in _BANNED:
            assert token not in text, f"{path.name} still references retired token {token!r}"
