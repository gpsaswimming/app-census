#!/usr/bin/env bash
# Vendor the swimparse CLI into ./vendor/swimparse for the ingest Docker build.
#
# swimparse is the ONE parser and lives in app-tools; app-census consumes it.
# Until it's published (e.g. as @gpsa/swimparse on a registry), we copy a
# snapshot into the build context. vendor/ is gitignored — this is a build
# artifact, not a second committed copy of the parser.
#
# Usage: scripts/vendor-swimparse.sh [path-to-app-tools/swimparse]
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
src="${1:-$here/../app-tools/swimparse}"
dst="$here/vendor/swimparse"

if [[ ! -f "$src/cli.js" ]]; then
  echo "swimparse not found at: $src" >&2
  echo "pass the path to app-tools/swimparse as the first argument" >&2
  exit 1
fi

rm -rf "$dst"
mkdir -p "$dst"
# Only the runtime pieces (zero-dep): CLI + src + package.json. Skip tests.
cp "$src/cli.js" "$src/package.json" "$dst/"
cp -R "$src/src" "$dst/src"
cp -R "$src/leagues" "$dst/leagues"

echo "vendored swimparse -> $dst"
