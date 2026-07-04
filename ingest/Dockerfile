# Ingest service image.
# Phase 0: Python-only shell (health endpoint).
# Phase 3: add a Node runtime + vendored swimparse CLI so the container can
#          parse .sd3/.hy3 itself (the parse boundary), and the DB client libs.
FROM python:3.12-slim

WORKDIR /app

COPY ingest/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Ship the ingest code and the league profiles it passes into swimparse.
COPY ingest/ ./ingest/
COPY leagues/ ./leagues/

EXPOSE 8000
# Non-root at runtime.
RUN useradd --uid 10001 --no-create-home appuser
USER 10001

CMD ["uvicorn", "ingest.app:app", "--host", "0.0.0.0", "--port", "8000"]
