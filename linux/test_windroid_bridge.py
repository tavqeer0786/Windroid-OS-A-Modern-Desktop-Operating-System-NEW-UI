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

class TestPhase2NativeInstallerEngine(unittest.TestCase):

    def test_installer_status_initial(self):
        res = wb.get_installer_status_impl()
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "idle")
        self.assertEqual(res["stage"], "idle")
        self.assertEqual(res["progress"], 0)
        self.assertTrue(res.get("canInstall", True))
        self.assertIn("bootMode", res)

    def test_installer_disks_discovery(self):
        res = wb.get_installer_disks_impl()
        self.assertTrue(res["success"])
        self.assertIsInstance(res.get("disks"), list)
        self.assertIsInstance(res.get("eligibleDisks"), list)
        self.assertIsInstance(res.get("excludedDevices"), list)

    def test_format_partition_device_path(self):
        self.assertEqual(wb.format_partition_device_path("/dev/sda", 1), "/dev/sda1")
        self.assertEqual(wb.format_partition_device_path("/dev/sda", 2), "/dev/sda2")
        self.assertEqual(wb.format_partition_device_path("/dev/nvme0n1", 1), "/dev/nvme0n1p1")
        self.assertEqual(wb.format_partition_device_path("/dev/nvme0n1", 2), "/dev/nvme0n1p2")
        self.assertEqual(wb.format_partition_device_path("/dev/mmcblk0", 1), "/dev/mmcblk0p1")

    def test_generate_plan_requires_target_disk(self):
        res = wb.generate_installer_plan_impl({"targetDisk": ""})
        self.assertFalse(res["success"])
        self.assertIn("Target disk selection is required", res.get("errors", [""])[0])

    def test_generate_plan_valid_disk(self):
        res = wb.generate_installer_plan_impl({
            "targetDisk": "/dev/sda",
            "installationMode": "erase_disk",
            "userConfig": {"username": "windroid", "deviceName": "Windroid-PC"},
            "localeConfig": {"language": "en_US.UTF-8", "keyboard": "us"}
        })
        self.assertTrue(res["success"])
        self.assertIsNotNone(res.get("plan"))
        self.assertTrue(len(res.get("authToken", "")) > 0)
        plan = res["plan"]
        self.assertEqual(plan["targetDisk"], "/dev/sda")
        self.assertEqual(plan["bootMode"], "uefi")
        self.assertEqual(len(plan["partitions"]), 2)
        # ESP
        self.assertEqual(plan["partitions"][0]["mountPoint"], "/boot/efi")
        self.assertEqual(plan["partitions"][0]["filesystem"], "fat32")
        # Root
        self.assertEqual(plan["partitions"][1]["mountPoint"], "/")
        self.assertEqual(plan["partitions"][1]["filesystem"], "ext4")

    def test_validate_plan(self):
        plan_res = wb.generate_installer_plan_impl({"targetDisk": "/dev/sda"})
        self.assertTrue(plan_res["success"])
        val_res = wb.validate_installer_plan_impl({"plan": plan_res["plan"]})
        self.assertTrue(val_res["success"])
        self.assertTrue(val_res["valid"])

    def test_authorize_plan(self):
        plan_res = wb.generate_installer_plan_impl({"targetDisk": "/dev/sda"})
        self.assertTrue(plan_res["success"])
        auth_res = wb.authorize_installer_plan_impl({"plan": plan_res["plan"]})
        self.assertTrue(auth_res["success"])
        self.assertTrue(len(auth_res.get("authToken", "")) > 0)

    def test_execute_plan_rejects_invalid_token(self):
        res = wb.execute_installer_plan_impl({
            "authToken": "invalid-token-123",
            "plan": {"targetDisk": "/dev/sda"}
        })
        self.assertFalse(res["success"])
        self.assertIn("UNAUTHORIZED_PLAN", res.get("error", ""))

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

