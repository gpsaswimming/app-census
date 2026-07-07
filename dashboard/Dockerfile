# Read-only Streamlit dashboard image.
FROM python:3.12-slim

WORKDIR /app

COPY dashboard/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# App code + the shared schema it queries, the league profile (age-band bounds),
# and the reference CSVs the QT tab reads (VPSU comparison standards).
COPY dashboard/ ./dashboard/
COPY db/ ./db/
COPY leagues/ ./leagues/
COPY data/ ./data/

EXPOSE 8501
RUN useradd --uid 10002 --no-create-home appuser
USER 10002

# Served at "/" behind the Caddy reverse proxy. XSRF/CORS are disabled because
# the websocket arrives via the proxy (same-origin to the browser, cross-origin
# to Streamlit); auth is the gateway's job (Pangolin), not Streamlit's.
CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.enableXsrfProtection=false", "--server.enableCORS=false"]
