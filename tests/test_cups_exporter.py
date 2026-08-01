import unittest
from unittest.mock import patch

import cups_exporter


class CupsExporterTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
