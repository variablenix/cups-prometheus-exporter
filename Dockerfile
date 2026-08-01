FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends cups-client curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 65532 exporter \
    && (getent group 7 >/dev/null || groupadd --system --gid 7 cups-socket) \
    && useradd --system --uid 65532 --gid exporter --groups 7 --no-create-home --shell /usr/sbin/nologin exporter

WORKDIR /app
COPY --chown=exporter:exporter cups_exporter.py /app/cups_exporter.py

USER exporter
EXPOSE 9628

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9628/healthz', timeout=3)"

ENTRYPOINT ["python3", "/app/cups_exporter.py"]
CMD ["--port", "9628"]
