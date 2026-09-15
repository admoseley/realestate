# API image. Debian 12 (bookworm) is pinned because Microsoft publishes its
# ODBC Driver 18 — required to reach Azure SQL — per Debian release.
FROM python:3.11-slim-bookworm

# poppler-utils: pdftotext, which parses sheriff-sale PDFs.
# msodbcsql18 + unixodbc: Azure SQL connectivity. curl/gnupg are only needed to
# add Microsoft's package repository, so they're removed afterwards.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg poppler-utils \
    && curl -sSL -o /tmp/packages-microsoft-prod.deb \
         https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc libgssapi-krb5-2 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY web/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy full project (analysis scripts + backend + logo live at repo root)
COPY . .

# Run from the backend directory so relative imports work
WORKDIR /app/web/backend

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
