FROM python:3.11-slim

# Install pdftotext (poppler-utils) and other system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
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
