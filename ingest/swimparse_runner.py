"""The parse boundary: shell out to the swimparse CLI.

app-census never parses SDIF/HY3 itself. It hands the raw bytes to swimparse
(the one parser, in app-tools) with the GPSA league profile and `--score`, and
gets back a DOB-free, age-grouped, scored NormalizedMeet. swimparse strips the
birthdates *before* the data crosses into Python — this call is the PII firewall.

The CLI is located via, in order:
  * ``SWIMPARSE_CLI`` env var (set to ``/app/vendor/swimparse/cli.js`` in the
    container image; see the Dockerfile),
  * the sibling checkout ``../app-tools/swimparse/cli.js`` (local dev).
Node is ``NODE_BIN`` or ``node`` on PATH.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from leagues import load_profile


class SwimparseError(RuntimeError):
    """Raised when the parser can't be run or rejects the file."""


def _find_cli() -> str:
    env = os.getenv("SWIMPARSE_CLI")
    candidates = [env] if env else []
    candidates.append(
        str(Path(__file__).resolve().parents[2] / "app-tools" / "swimparse" / "cli.js")
    )
    candidates.append("/app/vendor/swimparse/cli.js")
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise SwimparseError(
        "swimparse CLI not found; set SWIMPARSE_CLI or vendor it into the image"
    )


def parse_bytes(data: bytes, filename: str = "meet.sd3", league: str = "gpsa") -> dict:
    """Parse raw meet-result bytes into a DOB-free, scored NormalizedMeet dict."""
    cli = _find_cli()
    node = os.getenv("NODE_BIN", "node")
    profile = load_profile(league)

    # Preserve the extension so swimparse's format detection has the hint.
    suffix = Path(filename).suffix or ".sd3"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"input{suffix}"
        src.write_bytes(data)
        prof = Path(tmp) / "league.json"
        prof.write_text(json.dumps(profile), encoding="utf-8")

        proc = subprocess.run(
            [node, cli, str(src), "--league-file", str(prof), "--score"],
            capture_output=True,
            text=True,
        )
    if proc.returncode != 0:
        raise SwimparseError(proc.stderr.strip() or "swimparse failed to parse the file")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise SwimparseError(f"swimparse produced invalid JSON: {exc}") from exc
