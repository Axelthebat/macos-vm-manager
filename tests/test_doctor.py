# SPDX-License-Identifier: MIT
"""Tests for the host check."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from macosvm import doctor
from macosvm.config import Paths


class ReportTest(unittest.TestCase):
    def test_a_report_with_no_failures_is_ok(self) -> None:
        report = doctor.Report()
        report.add("a thing", doctor.OK, "fine")
        report.add("another", doctor.WARN, "hmm")
        self.assertFalse(report.failures)
        self.assertEqual(len(report.warnings), 1)
        self.assertTrue(report.as_dict()["ok"])

    def test_a_failure_makes_the_report_not_ok(self) -> None:
        report = doctor.Report()
        report.add("a thing", doctor.FAIL, "broken", "fix it")
        self.assertEqual(len(report.failures), 1)
        self.assertFalse(report.as_dict()["ok"])

    def test_a_check_says_what_it_is(self) -> None:
        report = doctor.Report()
        check = report.add("a thing", doctor.FAIL, "broken", "fix it")
        self.assertEqual(
            check.as_dict(),
            {"name": "a thing", "status": "fail", "detail": "broken", "fix": "fix it"},
        )


class ChecksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        os.environ["MACOSVM_CONFIG_DIR"] = str(self.root / "config")
        os.environ["MACOSVM_DATA_DIR"] = str(self.root / "data")
        os.environ["MACOSVM_CACHE_DIR"] = str(self.root / "cache")
        os.environ["REIMS_CTL_CONFIG_DIR"] = str(self.root / "config" / "reims-ctl")
        os.environ["REIMS_CTL_DATA_DIR"] = str(self.root / "data" / "reims-ctl")
        self.paths = Paths()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_the_checks_run_and_name_themselves(self) -> None:
        report = doctor.run_all(self.paths)
        names = {check.name for check in report.checks}
        for expected in ("System", "KVM", "vm.max_map_count", "Vulkan", "Rust"):
            self.assertIn(expected, names)

    def test_a_machine_without_the_tools_is_not_ok(self) -> None:
        # The tools are installed on this computer, so they are taken away
        # for the test: the check has to notice that they are missing.
        with mock.patch("macosvm.reims.find_tool", return_value=None):
            report = doctor.run_all(self.paths)
        tools = [check for check in report.checks if check.name in ("reims-ctl", "reims-util")]
        self.assertTrue(tools)
        self.assertTrue(all(check.status == doctor.FAIL for check in tools))
        self.assertTrue(all(check.fix for check in tools))

    def test_the_json_is_a_plain_object(self) -> None:
        report = doctor.run_all(self.paths)
        payload = report.as_dict()
        self.assertIn("checks", payload)
        self.assertIsInstance(payload["checks"], list)
        for check in payload["checks"]:
            self.assertEqual(set(check), {"name", "status", "detail", "fix"})


if __name__ == "__main__":
    unittest.main()
