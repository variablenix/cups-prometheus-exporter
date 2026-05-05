FROM python:3.12-slim

RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
    cups-client \
    curl && \
    rm -rf /var/lib/apt/lists/*

COPY cups_exporter.py /app/cups_exporter.py

EXPOSE 9628
CMD ["python3", "/app/cups_exporter.py", "--port", "9628"]
