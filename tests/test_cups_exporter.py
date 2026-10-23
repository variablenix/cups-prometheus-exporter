import unittest
import http.client
import socket
import threading
import time
from unittest.mock import patch

import cups_exporter


class CupsExporterTests(unittest.TestCase):
    @patch('cups_exporter.subprocess.run', side_effect=cups_exporter.subprocess.TimeoutExpired('lpstat', 10))
    def test_command_timeout_returns_unavailable(self, _run):
        self.assertEqual(cups_exporter.run_cmd(['lpstat', '-r']), ('', 1))

    @patch("cups_exporter.run_cmd")
    def test_cups_up_distinguishes_not_running(self, run_cmd):
        run_cmd.return_value = ("scheduler is not running", 0)
        self.assertEqual(cups_exporter.get_cups_up(), 0)

        run_cmd.return_value = ("scheduler is running", 0)
        self.assertEqual(cups_exporter.get_cups_up(), 1)

    @patch("cups_exporter.run_cmd")
    def test_printer_status_parses_states_and_accepting_flag(self, run_cmd):
        run_cmd.return_value = (
            "printer Office-Printer is idle. enabled since Mon 01 Jan 00:00:00 2026\n"
            "Office-Printer not accepting requests since Mon 01 Jan 00:00:00 2026\n"
            "printer Label-Printer is processing. disabled since Mon 01 Jan 00:00:00 2026\n"
            "Label-Printer accepting requests since Mon 01 Jan 00:00:00 2026",
            0,
        )

        self.assertEqual(
            cups_exporter.get_printer_status(),
            [
                {"name": "Label-Printer", "status": 1, "accepting": 1, "enabled": 0},
                {"name": "Office-Printer", "status": 0, "accepting": 0, "enabled": 1},
            ],
        )

    def test_job_parser_handles_printer_names_with_hyphens(self):
        self.assertEqual(
            cups_exporter._printer_from_job_line("Brother-MFC-L3770CDW-42 user 1024 bytes"),
            "Brother-MFC-L3770CDW",
        )
        self.assertIsNone(cups_exporter._printer_from_job_line("not-a-job"))

    def test_label_values_are_escaped_for_prometheus(self):
        self.assertEqual(cups_exporter._escape_label_value('a\\b"c\nd'), 'a\\\\b\\"c\\nd')

    @patch("cups_exporter.get_job_counts", return_value={"Office-Printer": {"active": 2, "completed": 4}})
    @patch("cups_exporter.get_printer_status")
    @patch("cups_exporter.get_cups_up", return_value=1)
    def test_metrics_are_prometheus_text(self, cups_up, printer_status, _job_counts):
        printer_status.return_value = [
            {"name": "Office-Printer", "status": 0, "accepting": 1, "enabled": 1}
        ]

        output = cups_exporter.generate_metrics()

        self.assertIn("# TYPE cups_jobs_completed gauge", output)
        self.assertIn('cups_jobs_active{printer="Office-Printer"} 2', output)
        self.assertIn('cups_jobs_completed{printer="Office-Printer"} 4', output)
        cups_up.assert_called_once_with()


class HttpResourceTests(unittest.TestCase):
    def setUp(self):
        self.server = cups_exporter.ThreadingHTTPServer(
            ('127.0.0.1', 0), cups_exporter.MetricsHandler,
            max_workers=1, request_timeout=0.5)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.address = self.server.server_address

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_health_response_closes_keepalive_connection(self):
        with socket.create_connection(self.address, timeout=2) as client:
            client.sendall(b'GET /healthz HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n')
            response = http.client.HTTPResponse(client)
            response.begin()
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader('Connection'), 'close')
            self.assertEqual(response.read(), b'ok\n')
            self.assertEqual(client.recv(1), b'')

    def test_idle_client_times_out_and_releases_worker(self):
        with socket.create_connection(self.address, timeout=2) as idle:
            idle.sendall(b'GET /healthz HTTP/1.1\r\n')
            self.assertEqual(idle.recv(1), b'')
        connection = http.client.HTTPConnection(*self.address, timeout=2)
        try:
            connection.request('GET', '/healthz')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
        finally:
            connection.close()

    def test_busy_server_closes_excess_connections(self):
        with socket.create_connection(self.address, timeout=2) as first:
            first.sendall(b'GET /healthz HTTP/1.1\r\n')
            deadline = time.monotonic() + 0.4
            while self.server._worker_slots._value and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertEqual(self.server._worker_slots._value, 0)
            with socket.create_connection(self.address, timeout=2) as excess:
                self.assertEqual(excess.recv(1), b'')

    def test_invalid_absolute_request_target_returns_bad_request(self):
        with socket.create_connection(self.address, timeout=2) as client:
            client.sendall(b'GET http://[invalid HTTP/1.1\r\nHost: localhost\r\n\r\n')
            response = http.client.HTTPResponse(client)
            response.begin()
            self.assertEqual(response.status, 400)
            response.read()


if __name__ == "__main__":
    unittest.main()
