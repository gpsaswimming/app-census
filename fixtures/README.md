# Fixtures

Sanitized, **DOB-free** `NormalizedMeet` JSON emitted by swimparse with the GPSA
league profile applied (`swimparse --league gpsa`). Used by ingest/schema tests
so development never touches real swimmer data.

**Never commit raw `.sd3`/`.hy3` here** — they carry minors' birthdates. The
`.gitignore` blocks those extensions; only sanitized JSON belongs in this public
repo. See the fixture-sanitization guardrail.

To (re)generate from a sanitized swimparse fixture:

```bash
node ../app-tools/swimparse/cli.js \
  ../app-tools/swimparse/test/fixtures/gg-at-ww.hy3 \
  --league gpsa --pretty > gg-at-ww.census.json
```
