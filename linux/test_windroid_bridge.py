#!/usr/bin/env python3
import sys
import os
import unittest
import tempfile
import json
import shutil

# Import functions from windroid-bridge and windroid-first-boot
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import importlib.util

spec_wb = importlib.util.spec_from_file_location("windroid_bridge", os.path.join(os.path.dirname(__file__), "windroid-bridge.py"))
wb = importlib.util.module_from_spec(spec_wb)
spec_wb.loader.exec_module(wb)

spec_fb = importlib.util.spec_from_file_location("windroid_first_boot", os.path.join(os.path.dirname(__file__), "windroid-first-boot.py"))
fb = importlib.util.module_from_spec(spec_fb)
spec_fb.loader.exec_module(fb)

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
            "installationCompletedAt": "2026-08-14T10:00:00Z",
            "oobeCompleted": True,
            "oobeCompletedAt": "2026-08-14T10:05:00Z"
        }
        valid, err = wb.validate_native_installer_state_data(state)
        self.assertFalse(valid)
        self.assertIn("reserved username", err)

class TestFirstBootOrchestratorAndOobeHandoff(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.test_dir, "installer-state.json")
        fb.STATE_FILE = self.state_file
        fb.STATE_BACKUP_FILE = os.path.join(self.test_dir, "installation-state.json")
        fb.LIGHTDM_CONF_DIR = os.path.join(self.test_dir, "lightdm.conf.d")
        fb.LIGHTDM_AUTOLOGIN_CONF = os.path.join(fb.LIGHTDM_CONF_DIR, "80-windroid-autologin.conf")
        fb.LIGHTDM_OOBE_CONF = os.path.join(fb.LIGHTDM_CONF_DIR, "80-windroid-oobe.conf")
        fb.LIGHTDM_LIVE_CONF = os.path.join(fb.LIGHTDM_CONF_DIR, "80-windroid-live-autologin.conf")
        fb.RUNTIME_MODE_FILE = os.path.join(self.test_dir, "runtime-mode")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_state_persistence(self):
        state_data = {
            "version": "windroid-installer-state-v1",
            "state": "OOBE_PENDING",
            "installationCompleted": True,
            "oobeCompleted": False
        }
        ok = fb.save_installer_state_atomic(state_data, self.test_dir)
        self.assertTrue(ok)
        saved = fb.load_installer_state(os.path.join(self.test_dir, "var/lib/windroid/installer-state.json"))
        self.assertEqual(saved["state"], "OOBE_PENDING")
        self.assertTrue(saved["installationCompleted"])

    def test_lightdm_oobe_config_generation(self):
        fb.configure_lightdm_oobe()
        self.assertTrue(os.path.exists(fb.LIGHTDM_OOBE_CONF))
        with open(fb.LIGHTDM_OOBE_CONF, "r") as f:
            content = f.read()
        self.assertIn("autologin-user=windroid-oobe", content)
        self.assertNotIn("autologin-user=root", content)
        self.assertNotIn("autologin-user=user\n", content)

    def test_lightdm_real_user_config_generation(self):
        fb.configure_lightdm_real_user("johndoe")
        self.assertTrue(os.path.exists(fb.LIGHTDM_AUTOLOGIN_CONF))
        with open(fb.LIGHTDM_AUTOLOGIN_CONF, "r") as f:
            content = f.read()
        self.assertIn("autologin-user=johndoe", content)
        self.assertFalse(os.path.exists(fb.LIGHTDM_OOBE_CONF))

    def test_reject_invalid_usernames_in_lightdm_real_user(self):
        self.assertFalse(fb.configure_lightdm_real_user(""))
        self.assertFalse(fb.configure_lightdm_real_user("root"))
        self.assertFalse(fb.configure_lightdm_real_user("user"))
        self.assertFalse(fb.configure_lightdm_real_user("windroid-oobe"))

    def test_complete_oobe_rejects_temporary_and_reserved_usernames(self):
        res1 = wb.complete_oobe_impl({"username": "windroid-oobe"})
        self.assertFalse(res1["success"])
        self.assertIn("reserved", res1["error"])

        res2 = wb.complete_oobe_impl({"username": "root"})
        self.assertFalse(res2["success"])
        self.assertIn("reserved", res2["error"])

        res3 = wb.complete_oobe_impl({"username": "user"})
        self.assertFalse(res3["success"])
        self.assertIn("reserved", res3["error"])

        res4 = wb.complete_oobe_impl({"username": "Invalid User!"})
        self.assertFalse(res4["success"])
        self.assertIn("Invalid username format", res4["error"])

    def test_no_fake_bootloader_stubs_in_codebase(self):
        bridge_file = os.path.join(os.path.dirname(__file__), "windroid-bridge.py")
        with open(bridge_file, "r") as f:
            content = f.read()
        self.assertNotIn("WINDROID_BOOTX64_STUB", content, "Fake bootloader binary stub found in windroid-bridge.py")

if __name__ == "__main__":
    unittest.main()
