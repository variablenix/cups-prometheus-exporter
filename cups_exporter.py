#!/usr/bin/env python3
"""
cups_exporter.py — Prometheus exporter for CUPS print server metrics.
Exposes printer status, job counts, and queue stats via HTTP on port 9628.

Usage:
    python3 cups_exporter.py [--port 9628]

Metrics exposed:
    cups_printer_status         - Printer state (0=idle, 1=printing, 2=stopped/error)
    cups_printer_accepting      - Whether printer is accepting jobs (0/1)
    cups_printer_enabled        - Whether printer is enabled (0/1)
    cups_jobs_total             - Total jobs completed (counter, resets on CUPS restart)
    cups_jobs_active            - Currently active/pending jobs per printer
    cups_up                     - Whether CUPS scheduler is reachable (0/1)
"""

import subprocess
import re
import time
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler


# ── Metric definitions ────────────────────────────────────────────────────────

METRICS_HELP = {
    "cups_up": "# HELP cups_up Whether the CUPS scheduler is running\n# TYPE cups_up gauge",
    "cups_printer_status": "# HELP cups_printer_status Printer state: 0=idle, 1=printing, 2=stopped\n# TYPE cups_printer_status gauge",
    "cups_printer_accepting": "# HELP cups_printer_accepting Whether the printer is accepting jobs\n# TYPE cups_printer_accepting gauge",
    "cups_printer_enabled": "# HELP cups_printer_enabled Whether the printer is enabled\n# TYPE cups_printer_enabled gauge",
    "cups_jobs_active": "# HELP cups_jobs_active Number of active/pending jobs per printer\n# TYPE cups_jobs_active gauge",
    "cups_jobs_completed": "# HELP cups_jobs_completed Total completed jobs per printer since CUPS start\n# TYPE cups_jobs_completed counter",
}


# ── CUPS data collection ──────────────────────────────────────────────────────

def run_cmd(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip(), result.returncode
    except Exception:
        return "", 1


def get_cups_up():
    out, rc = run_cmd(["lpstat", "-r"])
    return 1 if rc == 0 and "running" in out else 0


def get_printer_status():
    """
    Returns list of dicts:
      { name, status, accepting, enabled }
    """
    out, rc = run_cmd(["lpstat", "-p", "-a"])
    if rc != 0:
        return []

    printers = {}

    for line in out.splitlines():
        # printer Brother-MFC-L3770CDW is idle. enabled since ...
        m = re.match(r"^printer (\S+) is (\w+)", line)
        if m:
            name = m.group(1)
            state_str = m.group(2).lower()
            if name not in printers:
                printers[name] = {"name": name, "status": 0, "accepting": 1, "enabled": 1}
            if state_str == "idle":
                printers[name]["status"] = 0
            elif state_str in ("printing", "processing"):
                printers[name]["status"] = 1
            else:
                printers[name]["status"] = 2
            printers[name]["enabled"] = 0 if "disabled" in line else 1

        # Brother-MFC-L3770CDW accepting requests since ...
        m = re.match(r"^(\S+) (accepting|not accepting) requests", line)
        if m:
            name = m.group(1)
            if name not in printers:
                printers[name] = {"name": name, "status": 0, "accepting": 1, "enabled": 1}
            printers[name]["accepting"] = 1 if m.group(2) == "accepting" else 0

    return list(printers.values())


def get_job_counts():
    """
    Returns dict: { printer_name: { active: N, completed: N } }
    """
    counts = {}

    # Active jobs
    out, _ = run_cmd(["lpstat", "-o"])
    for line in out.splitlines():
        # Brother-MFC-L3770CDW-42 ak 1024 ...
        m = re.match(r"^(\S+)-\d+\s+", line)
        if m:
            printer = m.group(1)
            counts.setdefault(printer, {"active": 0, "completed": 0})
            counts[printer]["active"] += 1

    # Completed jobs (requires EnableJobHistory Yes in cupsd.conf)
    out, _ = run_cmd(["lpstat", "-W", "completed", "-o"])
    for line in out.splitlines():
        m = re.match(r"^(\S+)-\d+\s+", line)
        if m:
            printer = m.group(1)
            counts.setdefault(printer, {"active": 0, "completed": 0})
            counts[printer]["completed"] += 1

    return counts


# ── Prometheus output ─────────────────────────────────────────────────────────

def generate_metrics():
    lines = []

    cups_up = get_cups_up()
    lines.append(METRICS_HELP["cups_up"])
    lines.append(f"cups_up {cups_up}")

    if cups_up == 0:
        return "\n".join(lines) + "\n"

    printers = get_printer_status()
    job_counts = get_job_counts()

    lines.append(METRICS_HELP["cups_printer_status"])
    for p in printers:
        lines.append(f'cups_printer_status{{printer="{p["name"]}"}} {p["status"]}')

    lines.append(METRICS_HELP["cups_printer_accepting"])
    for p in printers:
        lines.append(f'cups_printer_accepting{{printer="{p["name"]}"}} {p["accepting"]}')

    lines.append(METRICS_HELP["cups_printer_enabled"])
    for p in printers:
        lines.append(f'cups_printer_enabled{{printer="{p["name"]}"}} {p["enabled"]}')

    lines.append(METRICS_HELP["cups_jobs_active"])
    for p in printers:
        n = p["name"]
        active = job_counts.get(n, {}).get("active", 0)
        lines.append(f'cups_jobs_active{{printer="{n}"}} {active}')

    lines.append(METRICS_HELP["cups_jobs_completed"])
    for p in printers:
        n = p["name"]
        completed = job_counts.get(n, {}).get("completed", 0)
        lines.append(f'cups_jobs_completed{{printer="{n}"}} {completed}')

    return "\n".join(lines) + "\n"


# ── HTTP server ───────────────────────────────────────────────────────────────

class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            output = generate_metrics()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.end_headers()
            self.wfile.write(output.encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<a href='/metrics'>metrics</a>")

    def log_message(self, format, *args):
        pass  # suppress access logs


def main():
    parser = argparse.ArgumentParser(description="CUPS Prometheus Exporter")
    parser.add_argument("--port", type=int, default=9628, help="Port to listen on (default: 9628)")
    args = parser.parse_args()

    print(f"cups_exporter listening on :{args.port}/metrics")
    server = HTTPServer(("0.0.0.0", args.port), MetricsHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
