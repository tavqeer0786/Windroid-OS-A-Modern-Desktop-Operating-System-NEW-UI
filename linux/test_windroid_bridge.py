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

    def test_valid_installer_state(self):
        state = {
            "version": "windroid-installer-state-v1",
            "state": "INSTALLER",
            "updatedAt": "2026-08-14T10:00:00Z",
            "installationCompleted": False,
            "oobeCompleted": False
        }
        valid, err = wb.validate_native_installer_state_data(state)
        self.assertTrue(valid, f"Expected valid INSTALLER state, got: {err}")

    def test_invalid_installer_state_marked_completed(self):
        state = {
            "version": "windroid-installer-state-v1",
            "state": "INSTALLER",
            "installationCompleted": True,
            "oobeCompleted": False
        }
        valid, err = wb.validate_native_installer_state_data(state)
        self.assertFalse(valid)
        self.assertIn("installationCompleted must be false", err)

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
        fb.LOG_FILE = os.path.join(self.test_dir, "windroid-first-boot.log")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_state_persistence(self):
        state_data = {
            "version": "windroid-installer-state-v1",
            "state": "OOBE_PENDING",
            "installationCompleted": True,
            "installationCompletedAt": "2026-08-14T10:00:00Z",
            "oobeCompleted": False,
            "userConfig": None
        }
        ok = fb.save_installer_state_atomic(state_data, self.test_dir)
        self.assertTrue(ok)
        saved = fb.load_installer_state(os.path.join(self.test_dir, "var/lib/windroid/installer-state.json"))
        self.assertEqual(saved["state"], "OOBE_PENDING")
        self.assertTrue(saved["installationCompleted"])

    def test_backup_state_recovery_when_primary_corrupt(self):
        # Write corrupted primary
        with open(self.state_file, "w") as f:
            f.write("corrupted json {")

        # Write valid backup
        valid_backup = {
            "version": "windroid-installer-state-v1",
            "state": "OOBE_PENDING",
            "installationCompleted": True,
            "installationCompletedAt": "2026-08-14T10:00:00Z",
            "oobeCompleted": False,
            "userConfig": None
        }
        with open(fb.STATE_BACKUP_FILE, "w") as f:
            json.dump(valid_backup, f)

        loaded = fb.load_installer_state(self.state_file)
        self.assertEqual(loaded["state"], "OOBE_PENDING")
        self.assertTrue(loaded["installationCompleted"])

    def test_fail_closed_when_both_states_corrupt(self):
        with open(self.state_file, "w") as f:
            f.write("corrupted json {")
        with open(fb.STATE_BACKUP_FILE, "w") as f:
            f.write("corrupted backup {")

        loaded = fb.load_installer_state(self.state_file)
        self.assertEqual(loaded["state"], "FAILED")

    def test_lightdm_oobe_config_generation(self):
        fb.configure_lightdm_oobe()
        self.assertTrue(os.path.exists(fb.LIGHTDM_OOBE_CONF))
        with open(fb.LIGHTDM_OOBE_CONF, "r") as f:
            content = f.read()
        self.assertIn("autologin-user=windroid-oobe", content)
        self.assertNotIn("autologin-user=root", content)
        self.assertNotIn("autologin-user=user\n", content)

    def test_lightdm_real_user_config_generation(self):
        # Mock user_exists for testing
        orig_user_exists = fb.user_exists
        try:
            fb.user_exists = lambda u: u == "johndoe"
            ok = fb.configure_lightdm_real_user("johndoe")
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(fb.LIGHTDM_AUTOLOGIN_CONF))
            with open(fb.LIGHTDM_AUTOLOGIN_CONF, "r") as f:
                content = f.read()
            self.assertIn("autologin-user=johndoe", content)
            self.assertFalse(os.path.exists(fb.LIGHTDM_OOBE_CONF))
        finally:
            fb.user_exists = orig_user_exists

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

    def test_cleanup_temporary_oobe_user_preconditions(self):
        # Fails when user does not exist
        self.assertFalse(fb.cleanup_temporary_oobe_user("nonexistentuser12345"))
        # Fails when username is root or windroid-oobe
        self.assertFalse(fb.cleanup_temporary_oobe_user("root"))
        self.assertFalse(fb.cleanup_temporary_oobe_user("windroid-oobe"))

    def test_save_native_installer_state_creates_primary_and_backup(self):
        tmp_target = tempfile.mkdtemp()
        try:
            res = wb.save_native_installer_state(tmp_target, "OOBE_PENDING", {
                "targetDisk": "/dev/sdb",
                "localeConfig": {"language": "en_US.UTF-8"}
            })
            self.assertTrue(res["success"])
            self.assertEqual(res["state"], "OOBE_PENDING")
            
            primary = os.path.join(tmp_target, "var/lib/windroid/installer-state.json")
            backup = os.path.join(tmp_target, "var/lib/windroid/installation-state.json")
            self.assertTrue(os.path.exists(primary))
            self.assertTrue(os.path.exists(backup))

            with open(primary, "r") as f:
                p_data = json.load(f)
            with open(backup, "r") as f:
                b_data = json.load(f)

            self.assertEqual(p_data["state"], "OOBE_PENDING")
            self.assertEqual(b_data["state"], "OOBE_PENDING")
            self.assertEqual(p_data["targetDisk"], "/dev/sdb")
            self.assertEqual(b_data["targetDisk"], "/dev/sdb")
            self.assertTrue(p_data["installationCompleted"])
            self.assertFalse(p_data["oobeCompleted"])
        finally:
            shutil.rmtree(tmp_target, ignore_errors=True)

    def test_load_native_installer_state_recovers_from_backup(self):
        tmp_target = tempfile.mkdtemp()
        try:
            var_lib = os.path.join(tmp_target, "var/lib/windroid")
            os.makedirs(var_lib, exist_ok=True)
            primary = os.path.join(var_lib, "installer-state.json")
            backup = os.path.join(var_lib, "installation-state.json")

            # Corrupt primary
            with open(primary, "w") as f:
                f.write("{invalid json")

            # Valid backup
            backup_data = {
                "version": "windroid-installer-state-v1",
                "state": "OOBE_PENDING",
                "updatedAt": "2026-08-16T12:00:00Z",
                "targetDisk": "/dev/sda",
                "localeConfig": {},
                "userConfig": None,
                "installationCompleted": True,
                "installationCompletedAt": "2026-08-16T12:00:00Z",
                "oobeCompleted": False,
                "oobeCompletedAt": None,
                "completedAt": "2026-08-16T12:00:00Z",
                "error": None
            }
            with open(backup, "w") as f:
                json.dump(backup_data, f)

            loaded = wb.load_native_installer_state(tmp_target)
            self.assertTrue(loaded["success"])
            self.assertEqual(loaded["state"], "OOBE_PENDING")
            self.assertEqual(loaded["targetDisk"], "/dev/sda")
        finally:
            shutil.rmtree(tmp_target, ignore_errors=True)

    def test_no_fake_bootloader_stubs_in_codebase(self):
        bridge_file = os.path.join(os.path.dirname(__file__), "windroid-bridge.py")
        with open(bridge_file, "r") as f:
            content = f.read()
        self.assertNotIn("WINDROID_BOOTX64_STUB", content, "Fake bootloader binary stub found in windroid-bridge.py")

    def test_state_machine_valid_and_invalid_transitions(self):
        # Valid transitions
        self.assertTrue(wb.is_valid_state_transition("INSTALLER", "INSTALLATION_IN_PROGRESS"))
        self.assertTrue(wb.is_valid_state_transition("INSTALLATION_IN_PROGRESS", "INSTALLATION_COMPLETE"))
        self.assertTrue(wb.is_valid_state_transition("INSTALLATION_COMPLETE", "OOBE_PENDING"))
        self.assertTrue(wb.is_valid_state_transition("OOBE_PENDING", "OOBE_IN_PROGRESS"))
        self.assertTrue(wb.is_valid_state_transition("OOBE_IN_PROGRESS", "OOBE_COMPLETE"))
        self.assertTrue(wb.is_valid_state_transition("OOBE_COMPLETE", "DESKTOP_READY"))
        self.assertTrue(wb.is_valid_state_transition("INSTALLER", "FAILED"))
        self.assertTrue(wb.is_valid_state_transition("INSTALLATION_IN_PROGRESS", "FAILED"))
        self.assertTrue(wb.is_valid_state_transition("OOBE_PENDING", "FAILED"))

        # Invalid transitions
        self.assertFalse(wb.is_valid_state_transition("DESKTOP_READY", "OOBE_PENDING"))
        self.assertFalse(wb.is_valid_state_transition("DESKTOP_READY", "INSTALLER"))
        self.assertFalse(wb.is_valid_state_transition("OOBE_COMPLETE", "INSTALLATION_IN_PROGRESS"))
        self.assertFalse(wb.is_valid_state_transition("INSTALLATION_COMPLETE", "INSTALLER"))
        self.assertFalse(wb.is_valid_state_transition("DESKTOP_READY", "INSTALLATION_IN_PROGRESS"))

    def test_partition_naming_for_all_supported_devices(self):
        self.assertEqual(wb.format_partition_device_path("/dev/sda", 1), "/dev/sda1")
        self.assertEqual(wb.format_partition_device_path("/dev/sda", 2), "/dev/sda2")
        self.assertEqual(wb.format_partition_device_path("/dev/vda", 1), "/dev/vda1")
        self.assertEqual(wb.format_partition_device_path("/dev/vda", 2), "/dev/vda2")
        self.assertEqual(wb.format_partition_device_path("/dev/nvme0n1", 1), "/dev/nvme0n1p1")
        self.assertEqual(wb.format_partition_device_path("/dev/nvme0n1", 2), "/dev/nvme0n1p2")
        self.assertEqual(wb.format_partition_device_path("/dev/mmcblk0", 1), "/dev/mmcblk0p1")
        self.assertEqual(wb.format_partition_device_path("/dev/mmcblk0", 2), "/dev/mmcblk0p2")
        self.assertEqual(wb.format_partition_device_path("/dev/loop0", 1), "/dev/loop0p1")

    def test_illegal_state_transition_raises_error_in_save(self):
        tmp_target = tempfile.mkdtemp()
        try:
            # 1. Start with DESKTOP_READY
            res = wb.save_native_installer_state(tmp_target, "DESKTOP_READY", {
                "targetDisk": "/dev/sda",
                "userConfig": {"username": "user1"}
            })
            self.assertTrue(res["success"])
            self.assertEqual(res["state"], "DESKTOP_READY")

            # 2. Attempt illegal transition to OOBE_PENDING
            with self.assertRaises(ValueError):
                wb.save_native_installer_state(tmp_target, "OOBE_PENDING", {})
        finally:
            shutil.rmtree(tmp_target, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
