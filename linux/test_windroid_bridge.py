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

class TestDeprecatedInstallerEndpoints(unittest.TestCase):

    def test_generate_plan_returns_deprecated(self):
        res = wb.generate_installer_plan_impl({"targetDisk": "/dev/sda"})
        self.assertFalse(res["success"])
        self.assertTrue(res.get("deprecated", False))
        self.assertIn("LEGACY_INSTALLER_REMOVED", res.get("error", ""))

    def test_validate_plan_returns_deprecated(self):
        res = wb.validate_installer_plan_impl({"plan": {}})
        self.assertFalse(res["success"])
        self.assertTrue(res.get("deprecated", False))
        self.assertIn("LEGACY_INSTALLER_REMOVED", res.get("error", ""))

    def test_authorize_plan_returns_deprecated(self):
        res = wb.authorize_installer_plan_impl({"plan": {}})
        self.assertFalse(res["success"])
        self.assertTrue(res.get("deprecated", False))
        self.assertIn("LEGACY_INSTALLER_REMOVED", res.get("error", ""))

    def test_execute_plan_returns_deprecated(self):
        res = wb.execute_installer_plan_impl({"plan": {}})
        self.assertFalse(res["success"])
        self.assertTrue(res.get("deprecated", False))
        self.assertIn("LEGACY_INSTALLER_REMOVED", res.get("error", ""))

    def test_installer_status_deprecated(self):
        res = wb.get_installer_status_impl()
        self.assertTrue(res["success"])
        self.assertTrue(res.get("deprecated", False))
        self.assertFalse(res.get("canInstall", True))

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
