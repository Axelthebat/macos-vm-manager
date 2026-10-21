# SPDX-License-Identifier: MIT
"""Tests for the VM registry, the listing, and the backups."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from macosvm import vms
from macosvm.config import Paths


def paths_in(root: Path) -> Paths:
    """A Paths that works on a throwaway tree."""
    os.environ["MACOSVM_CONFIG_DIR"] = str(root / "config")
    os.environ["MACOSVM_DATA_DIR"] = str(root / "data")
    os.environ["MACOSVM_CACHE_DIR"] = str(root / "cache")
    os.environ["REIMS_CTL_CONFIG_DIR"] = str(root / "config" / "reims-ctl")
    os.environ["REIMS_CTL_DATA_DIR"] = str(root / "data" / "reims-ctl")
    return Paths()


class RegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = paths_in(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_an_empty_registry_reads_as_empty(self) -> None:
        self.assertEqual(vms.read_registry(self.paths), [])

    def test_a_registry_survives_a_round_trip(self) -> None:
        entries = [{"name": "mac", "dir": "/home/user/vms/mac"}]
        vms.write_registry(self.paths, entries)
        self.assertEqual(vms.read_registry(self.paths), entries)

    def test_the_registry_is_written_the_way_reims_ctl_reads_it(self) -> None:
        vms.write_registry(self.paths, [{"name": "mac", "dir": "/vms/mac"}])
        text = self.paths.registry_file.read_text(encoding="utf-8")
        self.assertIn("[[vm]]", text)
        self.assertIn('name = "mac"', text)
        self.assertIn('dir = "/vms/mac"', text)

    def test_registering_twice_keeps_one_entry(self) -> None:
        vms.register(self.paths, "mac", Path("/vms/mac"))
        vms.register(self.paths, "mac", Path("/vms/mac"))
        self.assertEqual(len(vms.read_registry(self.paths)), 1)

    def test_unregistering_takes_the_entry_out(self) -> None:
        vms.register(self.paths, "mac", Path("/vms/mac"))
        vms.unregister(self.paths, "mac")
        self.assertEqual(vms.read_registry(self.paths), [])


class ListingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = paths_in(self.root)
        self.vm_dir = self.paths.vms_dir / "mac"
        self.vm_dir.mkdir(parents=True)
        (self.vm_dir / "vm.toml").write_text(
            "\n".join(
                [
                    'name = "mac"',
                    "cpus = 6",
                    "memory_mib = 16384",
                    'disk = "disk.qcow2"',
                    "",
                    "[display]",
                    'resolution = "2560x1600"',
                    "",
                    "[q35]",
                    'opencore = "OpenCore.qcow2"',
                    'installer = "installer.img"',
                    "",
                ]
            ),
            encoding="utf-8",
        )
        vms.register(self.paths, "mac", self.vm_dir)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_the_vm_is_listed(self) -> None:
        found = vms.list_vms(self.paths)
        self.assertEqual([vm.name for vm in found], ["mac"])

    def test_the_settings_are_read(self) -> None:
        vm = vms.list_vms(self.paths)[0]
        self.assertEqual(vm.cpus, 6)
        self.assertEqual(vm.memory, "16G")
        self.assertEqual(vm.resolution, "2560x1600")

    def test_a_vm_with_an_installer_is_waiting_for_one(self) -> None:
        vm = vms.list_vms(self.paths)[0]
        self.assertTrue(vm.has_installer)
        self.assertEqual(vm.state, "waiting for install")

    def test_a_vm_without_an_installer_is_ready(self) -> None:
        (self.vm_dir / "vm.toml").write_text('name = "mac"\ncpus = 4\n', encoding="utf-8")
        vm = vms.list_vms(self.paths)[0]
        self.assertFalse(vm.has_installer)
        self.assertEqual(vm.state, "ready")

    def test_a_pid_file_means_the_vm_runs(self) -> None:
        (self.vm_dir / "qemu.pid").write_text("1234\n", encoding="utf-8")
        vm = vms.list_vms(self.paths)[0]
        self.assertTrue(vm.running)
        self.assertEqual(vm.state, "running")

    def test_a_missing_vm_is_not_found(self) -> None:
        self.assertIsNone(vms.find_vm(self.paths, "nope"))

    def test_a_missing_vm_raises_when_it_is_asked_for_by_name(self) -> None:
        with self.assertRaises(LookupError):
            vms.resolve_vm(self.paths, "nope")


class BackupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = paths_in(self.root)
        self.vm_dir = self.paths.vms_dir / "mac"
        (self.vm_dir / "logs").mkdir(parents=True)
        (self.vm_dir / "vm.toml").write_text('name = "mac"\ncpus = 4\n', encoding="utf-8")
        (self.vm_dir / "disk.qcow2").write_bytes(b"not really a disk")
        (self.vm_dir / "logs" / "qemu.log").write_text("hello\n", encoding="utf-8")
        vms.register(self.paths, "mac", self.vm_dir)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_a_backup_holds_the_vm_and_a_manifest(self) -> None:
        vm = vms.list_vms(self.paths)[0]
        archive = vms.backup(self.paths, vm)
        self.assertTrue(archive.exists())
        manifest = vms.read_backup(archive)
        self.assertEqual(manifest["name"], "mac")
        self.assertIn("created", manifest)

    def test_a_restored_vm_is_the_same_and_is_registered(self) -> None:
        vm = vms.list_vms(self.paths)[0]
        archive = vms.backup(self.paths, vm)
        vms.unregister(self.paths, "mac")
        shutil_rm(self.vm_dir)

        name = vms.restore(self.paths, archive)
        self.assertEqual(name, "mac")
        restored = self.paths.vms_dir / "mac"
        self.assertTrue((restored / "vm.toml").exists())
        self.assertTrue((restored / "logs" / "qemu.log").exists())
        self.assertEqual([entry["name"] for entry in vms.read_registry(self.paths)], ["mac"])

    def test_a_backup_can_be_restored_as_a_new_vm(self) -> None:
        vm = vms.list_vms(self.paths)[0]
        archive = vms.backup(self.paths, vm)
        name = vms.restore(self.paths, archive, as_new="outra")
        self.assertEqual(name, "outra")
        self.assertTrue((self.paths.vms_dir / "outra" / "vm.toml").exists())

    def test_restoring_onto_a_vm_that_is_there_refuses(self) -> None:
        vm = vms.list_vms(self.paths)[0]
        archive = vms.backup(self.paths, vm)
        with self.assertRaises(FileExistsError):
            vms.restore(self.paths, archive)

    def test_the_oldest_backups_are_pruned(self) -> None:
        vm = vms.list_vms(self.paths)[0]
        archives = [vms.backup(self.paths, vm) for _ in range(3)]
        vms.prune_backups(self.paths, 1)
        self.assertFalse(archives[0].exists())
        self.assertTrue(archives[-1].exists())


def shutil_rm(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
