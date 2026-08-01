#!/usr/bin/env python3
"""Prometheus exporter for CUPS printer and queue metrics."""

import argparse
import logging
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlsplit


LOGGER = logging.getLogger("cups_exporter")
COMMAND_TIMEOUT_SECONDS = float(os.getenv("CUPS_COMMAND_TIMEOUT_SECONDS", "10"))

METRICS_HELP = {
    "cups_up": "# HELP cups_up Whether the CUPS scheduler is running\n# TYPE cups_up gauge",
    "cups_printer_status": "# HELP cups_printer_status Printer state: 0=idle, 1=printing, 2=stopped\n# TYPE cups_printer_status gauge",
    "cups_printer_accepting": "# HELP cups_printer_accepting Whether the printer is accepting jobs\n# TYPE cups_printer_accepting gauge",
    "cups_printer_enabled": "# HELP cups_printer_enabled Whether the printer is enabled\n# TYPE cups_printer_enabled gauge",
    "cups_jobs_active": "# HELP cups_jobs_active Number of active/pending jobs per printer\n# TYPE cups_jobs_active gauge",
    "cups_jobs_completed": "# HELP cups_jobs_completed Number of completed jobs retained by CUPS per printer\n# TYPE cups_jobs_completed gauge",
}


def run_cmd(cmd):
    """Run a CUPS command and return its stdout and exit status."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
        return result.stdout.strip(), result.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        LOGGER.debug("CUPS command failed: %s", exc)
        return "", 1


def get_cups_up():
    out, rc = run_cmd(["lpstat", "-r"])
    return 1 if rc == 0 and re.search(r"\bis running\b", out.casefold()) else 0


def _get_printer(printers, name):
    return printers.setdefault(
        name,
        {"name": name, "status": 0, "accepting": 1, "enabled": 1},
    )


def get_printer_status():
    """Return printer state dictionaries parsed from ``lpstat`` output."""
    out, rc = run_cmd(["lpstat", "-p", "-a"])
    if rc != 0:
        return []

    printers = {}
    for line in out.splitlines():
        printer_match = re.match(r"^printer\s+(\S+)\s+is\s+([A-Za-z]+)\b", line, re.IGNORECASE)
        if printer_match:
            name, state = printer_match.groups()
            printer = _get_printer(printers, name)
            state = state.casefold()
            printer["status"] = 0 if state == "idle" else 1 if state in {"printing", "processing"} else 2
            printer["enabled"] = 0 if "disabled" in line.casefold() else 1

        accepting_match = re.match(
            r"^(\S+)\s+(accepting|not accepting)\s+requests\b",
            line,
            re.IGNORECASE,
        )
        if accepting_match:
            name, accepting = accepting_match.groups()
            printer = _get_printer(printers, name)
            printer["accepting"] = 0 if accepting.casefold() == "not accepting" else 1

    return [printers[name] for name in sorted(printers)]


def _printer_from_job_line(line):
    """Extract the printer from an lpstat job id such as ``printer-42``."""
    fields = line.split(maxsplit=1)
    if not fields:
        return None
    job_id = fields[0]
    printer, separator, job_number = job_id.rpartition("-")
    if separator and printer and job_number.isdigit():
        return printer
    return None


def get_job_counts():
    """Return ``{printer_name: {active, completed}}`` from CUPS job listings."""
    counts = {}

    for command, key in ((["lpstat", "-o"], "active"), (["lpstat", "-W", "completed", "-o"], "completed")):
        out, _ = run_cmd(command)
        for line in out.splitlines():
            printer = _printer_from_job_line(line)
            if printer:
                counts.setdefault(printer, {"active": 0, "completed": 0})[key] += 1

    return counts


def _escape_label_value(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _printer_metric(name, printer, value):
    label = _escape_label_value(printer["name"])
    return f'{name}{{printer="{label}"}} {value}'


def generate_metrics():
    """Collect and render all metrics in Prometheus text exposition format."""
    lines = [METRICS_HELP["cups_up"]]
    cups_up = get_cups_up()
    lines.append(f"cups_up {cups_up}")
    if not cups_up:
        return "\n".join(lines) + "\n"

    printers = get_printer_status()
    job_counts = get_job_counts()

    lines.append(METRICS_HELP["cups_printer_status"])
    lines.extend(_printer_metric("cups_printer_status", printer, printer["status"]) for printer in printers)

    lines.append(METRICS_HELP["cups_printer_accepting"])
    lines.extend(_printer_metric("cups_printer_accepting", printer, printer["accepting"]) for printer in printers)

    lines.append(METRICS_HELP["cups_printer_enabled"])
    lines.extend(_printer_metric("cups_printer_enabled", printer, printer["enabled"]) for printer in printers)

    lines.append(METRICS_HELP["cups_jobs_active"])
    for printer in printers:
        active = job_counts.get(printer["name"], {}).get("active", 0)
        lines.append(_printer_metric("cups_jobs_active", printer, active))

    lines.append(METRICS_HELP["cups_jobs_completed"])
    for printer in printers:
        completed = job_counts.get(printer["name"], {}).get("completed", 0)
        lines.append(_printer_metric("cups_jobs_completed", printer, completed))

    return "\n".join(lines) + "\n"


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class MetricsHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_text(self, body, status=200, content_type="text/plain; charset=utf-8"):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/metrics":
            self._send_text(generate_metrics(), content_type="text/plain; version=0.0.4; charset=utf-8")
        elif path == "/healthz":
            self._send_text("ok\n")
        elif path == "/readyz":
            ready = get_cups_up()
            self._send_text("ready\n" if ready else "CUPS unavailable\n", status=200 if ready else 503)
        elif path == "/":
            self._send_text("cups-prometheus-exporter\n")
        else:
            self._send_text("not found\n", status=404)

    def log_message(self, *_args):
        return


def main():
    parser = argparse.ArgumentParser(description="CUPS Prometheus exporter")
    parser.add_argument("--port", type=int, default=9628, help="Port to listen on (default: 9628)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    server = ThreadingHTTPServer(("0.0.0.0", args.port), MetricsHandler)
    LOGGER.info("cups_exporter listening on :%s", args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    main()
