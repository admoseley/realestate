# API image. Debian 12 (bookworm) is pinned because Microsoft publishes its
# ODBC Driver 18 — required to reach Azure SQL — per Debian release.
FROM python:3.11-slim-bookworm

# Logs go straight to stdout, which Container Apps and Render collect. No .pyc
# files are written: the app user can't write into the code directories.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

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

# The API runs as an unprivileged system user, so a compromised process can't
# modify the code, the installed packages, or the system. The UID is fixed so
# platforms that require a numeric non-root user can verify it.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app/data --no-create-home \
         --shell /usr/sbin/nologin app

WORKDIR /app

# Dependencies first, so code changes don't invalidate this layer.
COPY web/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Only what the API runs: the shared analysis modules and logo at the repo root,
# plus the backend (.dockerignore drops its tests). The whole repository used to
# be copied in, deployment configs and docs included.
COPY investment_analyzer.py generate_pdf_report.py sheriff_sale_analyzer.py spot_check.py \
     estellawilson_logo.jpg ./
COPY web/backend ./web/backend

# The only writable directory, used by the local fallbacks: SQLite when
# AZURE_SQL_CONNECTION_STRING isn't set (as on Render until cutover), and
# report PDFs when REPORTS_BLOB_URL isn't set. In Azure both live in managed
# services. Per-job temporary files go to /tmp, which any user can write.
RUN mkdir -p /app/data/reports && chown -R app:app /app/data
ENV DB_PATH=/app/data/reports.db \
    REPORTS_DIR=/app/data/reports

USER 10001:10001
WORKDIR /app/web/backend
EXPOSE 8000

# - exec makes uvicorn PID 1, so it receives SIGTERM when a revision is replaced
#   and shuts down gracefully. The old shell-form CMD left a shell as PID 1,
#   which doesn't forward signals, so the platform had to kill the process.
# - --workers 1: startup migrations and orphaned-job cleanup assume a single
#   process (see main.py).
# - --proxy-headers with --forwarded-allow-ips '*': the container is reachable
#   only through the platform's ingress, which sets X-Forwarded-For/-Proto.
#   Uvicorn ignores those headers from non-local proxies unless told otherwise.
# - --timeout-graceful-shutdown 25: finish in-flight requests, but exit before
#   Container Apps force-kills at 30 seconds. Jobs cut off are marked failed at
#   the next startup.
# - PORT is honored for Render, which assigns one. Container Apps uses 8000.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --workers 1 --proxy-headers --forwarded-allow-ips '*' --timeout-graceful-shutdown 25"]
