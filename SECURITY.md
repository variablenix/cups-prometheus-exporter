# Security boundaries and maintenance

The exporter serves unauthenticated monitoring data. Restrict its published port
to trusted monitoring clients with network controls, or use an authenticated
reverse proxy. The built-in HTTP server is not an Internet-facing application
server. Printer labels are escaped, subprocess arguments are fixed lists, CUPS
commands have timeouts, and HTTP connections have bounded concurrency and idle
timeouts. These controls do not guarantee availability during every flood.

The container runs without root privileges or Linux capabilities, with a read-only
root filesystem. A read-only bind mount of a Unix socket does not restrict its
protocol operations. Keep CUPS administration authenticated, and give the exporter
only the socket group needed for status queries.

The image contains the CUPS client and Python standard library. It does not need
pip, ensurepip, setuptools, MessagePack, a CUPS daemon, IPP printer backend, or
Foomatic filters. CI checks that these unused components are absent and that the
effective OpenSSL trust store excludes the two exact incident anchors described
in [DSA-6572-1](https://lists.debian.org/debian-security-announce/2026/msg00487.html).

CI scans OS and language packages without a global advisory ignore list. Release
tags are promoted only after the exact candidate digest passes the certificate
policy and the scanner's fixable HIGH/CRITICAL gate. Weekly rebuilds pick up OS
package updates; Dependabot tracks the pinned Python image. Deployments must pull
and recreate their exporter after a new image is published.

Scanner findings for installed packages can remain when Debian has no fix in the
selected stable release. For example, [CVE-2026-34980](https://security-tracker.debian.org/tracker/CVE-2026-34980)
requires a shared PostScript queue served by cupsd, and
[CVE-2026-55453](https://security-tracker.debian.org/tracker/CVE-2026-55453) involves
the IPP printer backend and later filter execution. Those components are not in
this status-only exporter image. This assessment does not cover the separate
host CUPS server: keep that server patched and assess its queues, filters, printer
trust and network exposure independently. Do not equate a passing image gate with
the absence of every vulnerability in the host or deployment.
