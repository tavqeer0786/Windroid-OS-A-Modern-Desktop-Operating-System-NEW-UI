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

if __name__ == "__main__":
    unittest.main()
