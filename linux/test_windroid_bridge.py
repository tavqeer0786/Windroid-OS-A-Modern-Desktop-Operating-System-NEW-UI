#!/usr/bin/env python3
import sys
import os
import unittest

# Import functions from windroid-bridge
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import importlib.util

spec = importlib.util.spec_from_file_location("windroid_bridge", os.path.join(os.path.dirname(__file__), "windroid-bridge.py"))
wb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wb)

class TestInstallerPartitionPlanning(unittest.TestCase):

    def test_erase_disk_sda_partition_naming(self):
        parts = wb.build_default_erase_disk_partitions("/dev/sda")
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["device"], "/dev/sda1")
        self.assertEqual(parts[0]["mountPoint"], "/boot/efi")
        self.assertEqual(parts[0]["filesystem"], "fat32")
        self.assertEqual(parts[1]["device"], "/dev/sda2")
        self.assertEqual(parts[1]["mountPoint"], "/")
        self.assertEqual(parts[1]["filesystem"], "ext4")

    def test_erase_disk_nvme_partition_naming(self):
        parts = wb.build_default_erase_disk_partitions("/dev/nvme0n1")
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["device"], "/dev/nvme0n1p1")
        self.assertEqual(parts[0]["mountPoint"], "/boot/efi")
        self.assertEqual(parts[1]["device"], "/dev/nvme0n1p2")
        self.assertEqual(parts[1]["mountPoint"], "/")

    def test_erase_disk_mmcblk_partition_naming(self):
        parts = wb.build_default_erase_disk_partitions("/dev/mmcblk0")
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["device"], "/dev/mmcblk0p1")
        self.assertEqual(parts[0]["mountPoint"], "/boot/efi")
        self.assertEqual(parts[1]["device"], "/dev/mmcblk0p2")
        self.assertEqual(parts[1]["mountPoint"], "/")

    def test_generate_plan_erase_disk(self):
        res = wb.generate_installer_plan_impl({"targetDisk": "/dev/sda", "installationMode": "erase_disk"})
        plan = res["plan"]
        self.assertIsNotNone(plan)
        self.assertEqual(plan["targetDisk"], "/dev/sda")
        self.assertEqual(len(plan["partitions"]), 2)
        self.assertEqual(plan["partitions"][0]["mountPoint"], "/boot/efi")
        self.assertEqual(plan["partitions"][1]["mountPoint"], "/")

    def test_generate_plan_manual_without_custom_partitions_rejected(self):
        res = wb.generate_installer_plan_impl({"targetDisk": "/dev/sda", "installationMode": "manual"})
        self.assertFalse(res["success"])
        self.assertIn("MANUAL_PARTITIONING_UNSUPPORTED", res["errors"][0])

    def test_canonicalize_empty_erase_disk_plan(self):
        empty_plan = {
            "targetDisk": "/dev/sda",
            "installationMode": "erase_disk",
            "partitions": []
        }
        repaired = wb.canonicalize_plan(empty_plan)
        self.assertEqual(len(repaired["partitions"]), 2)
        self.assertEqual(repaired["partitions"][0]["mountPoint"], "/boot/efi")
        self.assertEqual(repaired["partitions"][1]["mountPoint"], "/")

    def test_validate_plan_missing_esp(self):
        plan = {
            "targetDisk": "/dev/sda",
            "bootMode": "uefi",
            "installationMode": "manual",
            "userConfig": {"username": "windroid"},
            "partitions": [
                {"device": "/dev/sda1", "mountPoint": "/", "filesystem": "ext4"}
            ]
        }
        val = wb._validate_plan_internal(plan)
        self.assertFalse(val["valid"])
        self.assertTrue(any("UEFI_ESP_REQUIRED" in e for e in val["errors"]))

    def test_validate_plan_missing_root(self):
        plan = {
            "targetDisk": "/dev/sda",
            "bootMode": "uefi",
            "installationMode": "manual",
            "userConfig": {"username": "windroid"},
            "partitions": [
                {"device": "/dev/sda1", "mountPoint": "/boot/efi", "filesystem": "fat32"}
            ]
        }
        val = wb._validate_plan_internal(plan)
        self.assertFalse(val["valid"])
        self.assertTrue(any("root '/'" in e for e in val["errors"]))

    def test_authorize_and_canonicalize(self):
        plan_without_parts = {
            "targetDisk": "/dev/sda",
            "installationMode": "erase_disk",
            "partitions": []
        }
        res = wb.authorize_installer_plan_impl({"plan": plan_without_parts})
        self.assertTrue("plan" in res)
        self.assertEqual(len(res["plan"]["partitions"]), 2)

class TestNativeInstallerStateValidation(unittest.TestCase):

    def test_valid_oobe_pending_state(self):
        state = {
            "version": "windroid-installer-state-v1",
            "state": "OOBE_PENDING",
            "updatedAt": "2026-08-14T10:00:00Z",
            "targetDisk": "/dev/sda",
            "localeConfig": {"language": "en_US.UTF-8"},
            "userConfig": None,
            "installationCompleted": True,
            "installationCompletedAt": "2026-08-14T10:00:00Z",
            "oobeCompleted": False,
            "oobeCompletedAt": None,
            "completedAt": "2026-08-14T10:00:00Z",
            "error": None
        }
        valid, err = wb.validate_native_installer_state_data(state)
        self.assertTrue(valid, f"Expected valid OOBE_PENDING state, got error: {err}")

    def test_invalid_oobe_pending_with_premature_user(self):
        state = {
            "version": "windroid-installer-state-v1",
            "state": "OOBE_PENDING",
            "updatedAt": "2026-08-14T10:00:00Z",
            "targetDisk": "/dev/sda",
            "localeConfig": {},
            "userConfig": {"username": "testuser"},
            "installationCompleted": True,
            "installationCompletedAt": "2026-08-14T10:00:00Z",
            "oobeCompleted": False
        }
        valid, err = wb.validate_native_installer_state_data(state)
        self.assertFalse(valid)
        self.assertIn("userConfig must be null", err)

    def test_valid_installation_in_progress(self):
        state = {
            "version": "windroid-installer-state-v1",
            "state": "INSTALLATION_IN_PROGRESS",
            "updatedAt": "2026-08-14T10:00:00Z",
            "targetDisk": "/dev/sda",
            "localeConfig": {},
            "userConfig": None,
            "installationCompleted": False,
            "oobeCompleted": False
        }
        valid, err = wb.validate_native_installer_state_data(state)
        self.assertTrue(valid, f"Expected valid INSTALLATION_IN_PROGRESS state, got: {err}")

    def test_valid_oobe_complete(self):
        state = {
            "version": "windroid-installer-state-v1",
            "state": "OOBE_COMPLETE",
            "updatedAt": "2026-08-14T10:00:00Z",
            "targetDisk": "/dev/sda",
            "localeConfig": {"language": "en_US.UTF-8"},
            "userConfig": {"username": "alex", "fullName": "Alex User", "deviceName": "Alex-PC"},
            "installationCompleted": True,
            "installationCompletedAt": "2026-08-14T10:00:00Z",
            "oobeCompleted": True,
            "oobeCompletedAt": "2026-08-14T10:05:00Z",
            "completedAt": "2026-08-14T10:05:00Z",
            "error": None
        }
        valid, err = wb.validate_native_installer_state_data(state)
        self.assertTrue(valid, f"Expected valid OOBE_COMPLETE state, got: {err}")

    def test_invalid_oobe_complete_reserved_user(self):
        state = {
            "version": "windroid-installer-state-v1",
            "state": "OOBE_COMPLETE",
            "updatedAt": "2026-08-14T10:00:00Z",
            "targetDisk": "/dev/sda",
            "localeConfig": {},
            "userConfig": {"username": "windroid-oobe"},
            "installationCompleted": True,
            "oobeCompleted": True,
            "oobeCompletedAt": "2026-08-14T10:05:00Z"
        }
        valid, err = wb.validate_native_installer_state_data(state)
        self.assertFalse(valid)
        self.assertIn("reserved username", err)

if __name__ == "__main__":
    unittest.main()
