# BiKing: the Flask app with its data, served by waitress. One process with threads, never several workers:
# the graph and the shade live in RAM (~600 MB).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NUMBA_CACHE_DIR=/tmp/numba

WORKDIR /app
COPY requirements-app.txt .
RUN pip install -r requirements-app.txt

RUN useradd --create-home biking
COPY app/ app/
COPY scenarios/ scenarios/
# writable: the live-data cache (last_live.json) is saved next to the data
COPY --chown=biking data/processed/ data/processed/
USER biking

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["python", "-m", "waitress", "--host", "0.0.0.0", "--port", "8000", "--threads", "8", "--call", "app:create_app"]
