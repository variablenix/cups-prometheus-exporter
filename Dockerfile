FROM python:3.14.9-slim-trixie@sha256:b347e2dcbc7f0b6f9fb7182e9da6a187fb10ae715e0692518c1aed0eec94a700

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Keep Debian packages current so the image receives security updates; Trivy
# scans the resulting image in CI. Hadolint's exact-version rule is therefore
# intentionally suppressed for this install step.
# The runtime uses only the standard library; pip-only workarounds would add
# unnecessary packages. Refresh existing OS packages as well as cups-client.
# hadolint ignore=DL3005,DL3008
RUN apt-get update \
    && apt-get upgrade --yes \
    && apt-get install --yes --no-install-recommends cups-client ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall --yes pip \
    && python -c 'import ensurepip, shutil; shutil.rmtree(ensurepip.__path__[0])' \
    && groupadd --system --gid 65532 exporter \
    && (getent group 7 >/dev/null || groupadd --system --gid 7 cups-socket) \
    && useradd --system --uid 65532 --gid exporter --groups 7 --no-create-home --shell /usr/sbin/nologin exporter

WORKDIR /app
COPY --chown=exporter:exporter cups_exporter.py /app/cups_exporter.py

# Keep the named user so Docker preserves its supplementary lp socket group.
# hadolint ignore=DL3066
USER exporter
EXPOSE 9628

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9628/healthz', timeout=3)"]

ENTRYPOINT ["python3", "/app/cups_exporter.py"]
CMD ["--port", "9628"]
