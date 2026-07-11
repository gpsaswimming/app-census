# Ingest service image: Python (FastAPI) + a Node runtime with the vendored
# swimparse CLI, so the container parses .sd3/.hy3 itself (the parse boundary).
#
# Vendor swimparse into ./vendor/swimparse before building:
#     scripts/vendor-swimparse.sh
# (swimparse is zero-dependency, so the copy is self-contained.)

FROM python:3.12-slim

# Node runtime, copied from the official image (no apt/nodesource needed).
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node

WORKDIR /app

COPY ingest/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# App code + the config it passes into swimparse + the shared db package.
COPY ingest/ ./ingest/
COPY leagues/ ./leagues/
COPY db/ ./db/
# Vendored parser (see scripts/vendor-swimparse.sh).
COPY vendor/swimparse/ ./vendor/swimparse/

ENV SWIMPARSE_CLI=/app/vendor/swimparse/cli.js

EXPOSE 8000
RUN useradd --uid 10001 --no-create-home appuser
USER 10001

# Migrate to head on startup, then serve (see ingest/entrypoint.sh).
CMD ["sh", "ingest/entrypoint.sh"]
