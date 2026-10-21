# SPDX-License-Identifier: MIT
"""Tests for the settings, and for the command line."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from macosvm import cli
from macosvm.config import DEFAULT_SETTINGS, Paths, load_settings, save_settings


class SettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        os.environ["MACOSVM_CONFIG_DIR"] = str(self.root / "config")
        os.environ["MACOSVM_DATA_DIR"] = str(self.root / "data")
        os.environ["MACOSVM_CACHE_DIR"] = str(self.root / "cache")
        self.paths = Paths()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_the_defaults_are_used_when_there_is_no_file(self) -> None:
        settings = load_settings(self.paths)
        self.assertEqual(settings["vm"]["cpus"], DEFAULT_SETTINGS["vm"]["cpus"])
        self.assertEqual(settings["backup"]["keep"], 3)

    def test_the_settings_survive_a_round_trip(self) -> None:
        settings = load_settings(self.paths)
        settings["vm"]["memory"] = "16G"
        save_settings(self.paths, settings)
        self.assertEqual(load_settings(self.paths)["vm"]["memory"], "16G")

    def test_a_broken_settings_file_falls_back_to_the_defaults(self) -> None:
        self.paths.ensure()
        self.paths.settings_file.write_text("this is not toml = = =", encoding="utf-8")
        self.assertEqual(load_settings(self.paths)["vm"]["memory"], "8G")

    def test_a_partial_file_keeps_the_other_defaults(self) -> None:
        self.paths.ensure()
        self.paths.settings_file.write_text("[vm]\ncpus = 12\n", encoding="utf-8")
        settings = load_settings(self.paths)
        self.assertEqual(settings["vm"]["cpus"], 12)
        self.assertEqual(settings["vm"]["memory"], "8G")


class ParserTest(unittest.TestCase):
    #: The arguments each command needs to be parsed at all.
    ARGS = {
        "create": ["mac"],
        "import": ["mac", "--disk", "/tmp/mac.qcow2"],
        "delete": ["mac"],
        "set": ["mac"],
        "restore": ["backup.tar.gz"],
        "network": [],
        "autostart": [],
    }

    def test_every_command_is_there(self) -> None:
        parser = cli.build_parser()
        for command in (
            "list",
            "create",
            "import",
            "delete",
            "start",
            "stop",
            "reset",
            "poweroff",
            "term",
            "show",
            "set",
            "backup",
            "restore",
            "doctor",
            "setup",
            "network",
            "autostart",
            "logs",
            "tui",
        ):
            with self.subTest(command=command):
                args = parser.parse_args([command, *self.ARGS.get(command, [])])
                self.assertTrue(hasattr(args, "func"))

    def test_the_create_options_are_read(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            ["create", "mac", "--macos", "tahoe", "--disk-size", "512G", "--cpus", "8", "--memory", "16G"]
        )
        self.assertEqual(args.name, "mac")
        self.assertEqual(args.macos, "tahoe")
        self.assertEqual(args.disk_size, "512G")
        self.assertEqual(args.cpus, 8)
        self.assertEqual(args.memory, "16G")

    def test_the_network_action_is_read(self) -> None:
        parser = cli.build_parser()
        self.assertEqual(parser.parse_args(["network", "on"]).action, "on")
        self.assertEqual(parser.parse_args(["network", "attach", "mac"]).action, "attach")

    def test_the_version_is_printed(self) -> None:
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["--version"])


if __name__ == "__main__":
    unittest.main()
