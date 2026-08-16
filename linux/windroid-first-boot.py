#!/usr/bin/env python3
"""
Windroid OS Installed First-Boot & OOBE Orchestrator
Production-Grade Boot-Chain Implementation (Phase 2B)

This service runs as root early before display-manager/lightdm on the INSTALLED system.
It is responsible for:
1. Verifying that execution is on the installed root filesystem (not Live ISO).
2. Authoritatively reading /var/lib/windroid/installer-state.json.
3. Orchestrating temporary unprivileged 'windroid-oobe' user & LightDM for OOBE.
4. Orchestrating real-user LightDM transition and temporary user cleanup on completion.
5. Guaranteeing idempotency and preventing any return to the Phase-1 installer.
"""

import sys
import os
import re
import json
import time
import shutil
import subprocess
import datetime

STATE_FILE = "/var/lib/windroid/installer-state.json"
STATE_BACKUP_FILE = "/var/lib/windroid/installation-state.json"
RUNTIME_MODE_FILE = "/etc/windroid/runtime-mode"
LOG_FILE = "/var/log/windroid-first-boot.log"
LIGHTDM_CONF_DIR = "/etc/lightdm/lightdm.conf.d"
LIGHTDM_AUTOLOGIN_CONF = os.path.join(LIGHTDM_CONF_DIR, "80-windroid-autologin.conf")
LIGHTDM_OOBE_CONF = os.path.join(LIGHTDM_CONF_DIR, "80-windroid-oobe.conf")
LIGHTDM_LIVE_CONF = os.path.join(LIGHTDM_CONF_DIR, "80-windroid-live-autologin.conf")

OOBE_USER = "windroid-oobe"
OOBE_GROUPS = ["video", "audio", "render", "input"]
REAL_USER_GROUPS = ["sudo", "video", "audio", "render", "netdev", "plugdev", "input"]

def log(msg: str):
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    entry = f"[{timestamp}] [Windroid First-Boot] {msg}"
    print(entry, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
            f.flush()
    except Exception:
        pass

def run_cmd(cmd, timeout=30):
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def is_live_environment() -> bool:
    """Check whether the current runtime environment is a Live ISO."""
    try:
        if os.path.exists("/proc/cmdline"):
            with open("/proc/cmdline", "r", encoding="utf-8") as f:
                cmdline = f.read()
                if "boot=live" in cmdline or "live-media" in cmdline:
                    return True
        if os.path.exists("/run/live/medium") or os.path.exists("/run/live") or os.path.exists("/cdrom"):
            return True
        if os.path.exists(RUNTIME_MODE_FILE):
            with open(RUNTIME_MODE_FILE, "r", encoding="utf-8") as f:
                if f.read().strip() == "live":
                    return True
    except Exception as e:
        log(f"Error checking live environment: {e}")
    return False

def load_installer_state(state_file_path: str = STATE_FILE) -> dict:
    """Safely loads authoritative installer state."""
    for path in [state_file_path, STATE_BACKUP_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "state" in data:
                        return data
            except Exception as e:
                log(f"Warning: Failed to parse state file {path}: {e}")
    return {
        "version": "windroid-installer-state-v1",
        "state": "NOT_INSTALLED",
        "installationCompleted": False,
        "oobeCompleted": False
    }

def save_installer_state_atomic(state_data: dict, target_root: str = "/") -> bool:
    """Persists installer state using strict atomic write semantics."""
    target_dir = os.path.join(target_root, "var/lib/windroid")
    os.makedirs(target_dir, exist_ok=True)
    target_file = os.path.join(target_dir, "installer-state.json")
    backup_file = os.path.join(target_dir, "installation-state.json")
    tmp_file = os.path.join(target_dir, "installer-state.json.tmp")

    state_data["updatedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload = json.dumps(state_data, indent=2)

    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())

        os.replace(tmp_file, target_file)
        shutil.copy2(target_file, backup_file)

        # Fsync parent directory
        dir_fd = os.open(target_dir, os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

        run_cmd(["sync"])
        return True
    except Exception as e:
        log(f"Error persisting installer state atomically: {e}")
        return False

def user_exists(username: str) -> bool:
    if not username:
        return False
    ok, out, _ = run_cmd(["getent", "passwd", username])
    return ok and bool(out)

def setup_temporary_oobe_user() -> bool:
    """Idempotently creates unprivileged temporary windroid-oobe user."""
    log(f"Ensuring temporary OOBE user '{OOBE_USER}' exists...")
    if not user_exists(OOBE_USER):
        # Create unprivileged account without sudo
        ok, _, err = run_cmd([
            "useradd",
            "-m",
            "-s", "/bin/bash",
            "-c", "Windroid OOBE Temporary Account",
            OOBE_USER
        ])
        if not ok and not user_exists(OOBE_USER):
            log(f"Failed to create OOBE user: {err}")
            return False

        # Set empty/unlocked password status for GUI login if needed
        run_cmd(["passwd", "-d", OOBE_USER])

    # Assign minimal GUI groups
    for grp in OOBE_GROUPS:
        run_cmd(["usermod", "-aG", grp, OOBE_USER])

    # Configure Openbox autostart for OOBE user
    user_home = f"/home/{OOBE_USER}"
    openbox_dir = os.path.join(user_home, ".config/openbox")
    os.makedirs(openbox_dir, exist_ok=True)
    autostart_path = os.path.join(openbox_dir, "autostart")
    with open(autostart_path, "w", encoding="utf-8") as f:
        f.write("#!/bin/sh\n# Windroid OOBE Autostart\n/usr/bin/windroid-shell-runner.sh &\n")
    os.chmod(autostart_path, 0o755)

    # Ensure ownership
    run_cmd(["chown", "-R", f"{OOBE_USER}:{OOBE_USER}", user_home])
    return True

def configure_lightdm_oobe():
    """Configures LightDM for temporary windroid-oobe graphical session."""
    os.makedirs(LIGHTDM_CONF_DIR, exist_ok=True)

    # Remove any inherited live ISO autologin config
    if os.path.exists(LIGHTDM_LIVE_CONF):
        try:
            os.remove(LIGHTDM_LIVE_CONF)
            log(f"Removed inherited live autologin config: {LIGHTDM_LIVE_CONF}")
        except Exception as e:
            log(f"Notice: Could not remove live autologin config: {e}")

    # Remove real user config if present during OOBE
    if os.path.exists(LIGHTDM_AUTOLOGIN_CONF):
        try:
            os.remove(LIGHTDM_AUTOLOGIN_CONF)
        except Exception:
            pass

    conf_content = (
        "# Windroid OS OOBE Session Configuration\n"
        "[Seat:*]\n"
        "autologin-guest=false\n"
        f"autologin-user={OOBE_USER}\n"
        "autologin-user-timeout=0\n"
        "user-session=openbox\n"
    )
    with open(LIGHTDM_OOBE_CONF, "w", encoding="utf-8") as f:
        f.write(conf_content)
    log(f"LightDM OOBE configuration written to {LIGHTDM_OOBE_CONF} (autologin-user={OOBE_USER})")

def configure_lightdm_real_user(username: str):
    """Configures LightDM for authenticated real user session."""
    if not username or username == OOBE_USER or username == "root" or username == "user":
        log(f"Error: Refusing to configure LightDM for invalid or temporary username: '{username}'")
        return False

    os.makedirs(LIGHTDM_CONF_DIR, exist_ok=True)

    # Clean up OOBE & Live configs
    for cfg in [LIGHTDM_OOBE_CONF, LIGHTDM_LIVE_CONF]:
        if os.path.exists(cfg):
            try:
                os.remove(cfg)
            except Exception:
                pass

    conf_content = (
        f"# Windroid OS Authenticated User Session Configuration\n"
        "[Seat:*]\n"
        "autologin-guest=false\n"
        f"autologin-user={username}\n"
        "autologin-user-timeout=0\n"
        "user-session=openbox\n"
    )
    with open(LIGHTDM_AUTOLOGIN_CONF, "w", encoding="utf-8") as f:
        f.write(conf_content)
    log(f"LightDM Real User configuration written to {LIGHTDM_AUTOLOGIN_CONF} (autologin-user={username})")
    return True

def cleanup_temporary_oobe_user():
    """Safely removes temporary windroid-oobe account after real user is verified."""
    if not user_exists(OOBE_USER):
        log(f"Temporary user '{OOBE_USER}' is already absent.")
        return True

    log(f"Safely removing temporary user account '{OOBE_USER}'...")
    # Kill any dangling processes for windroid-oobe
    run_cmd(["pkill", "-9", "-u", OOBE_USER])
    time.sleep(0.5)

    # Delete user and home
    ok, _, err = run_cmd(["userdel", "-r", OOBE_USER])
    if not ok:
        log(f"Notice during userdel of {OOBE_USER}: {err}")

    # Double-check
    exists = user_exists(OOBE_USER)
    if exists:
        log(f"Warning: {OOBE_USER} still present after deletion attempt.")
        return False

    log(f"Temporary user '{OOBE_USER}' successfully cleaned up.")
    return True

def orchestrate_first_boot():
    """Main orchestration entry point."""
    log("==================================================")
    log("WINDROID OS FIRST-BOOT ORCHESTRATOR STARTING")
    log("==================================================")

    # 1. Guard against running on Live ISO
    if is_live_environment():
        log("Execution detected on LIVE ISO environment. First-boot orchestrator exiting cleanly.")
        return 0

    # Ensure /etc/windroid/runtime-mode is 'installed'
    os.makedirs("/etc/windroid", exist_ok=True)
    with open(RUNTIME_MODE_FILE, "w", encoding="utf-8") as f:
        f.write("installed\n")

    # 2. Load Authoritative State
    state = load_installer_state()
    current_state = state.get("state", "NOT_INSTALLED")
    log(f"Authoritative installer state: {current_state}")

    if current_state == "INSTALLATION_IN_PROGRESS":
        log("ERROR: Installation was left in an incomplete state (INSTALLATION_IN_PROGRESS). Halting to prevent damage.")
        return 1

    elif current_state == "FAILED":
        log("ERROR: Installation previously failed. Halting OOBE transition.")
        return 1

    elif current_state in ["OOBE_PENDING", "OOBE_IN_PROGRESS"]:
        log(f"Handling state '{current_state}': Preparing temporary OOBE session.")
        
        # Ensure temporary OOBE user exists
        if not setup_temporary_oobe_user():
            log("FATAL: Could not prepare temporary OOBE user.")
            return 1

        # Configure LightDM for OOBE
        configure_lightdm_oobe()

        # Update state to OOBE_IN_PROGRESS if it was OOBE_PENDING
        if current_state == "OOBE_PENDING":
            state["state"] = "OOBE_IN_PROGRESS"
            save_installer_state_atomic(state)
            log("Transitioned state to OOBE_IN_PROGRESS.")

        log("OOBE preparation complete. Ready for LightDM graphical session.")
        return 0

    elif current_state in ["OOBE_COMPLETE", "DESKTOP_READY"]:
        user_config = state.get("userConfig") or {}
        username = user_config.get("username", "")

        log(f"Handling state '{current_state}': Verifying real user '{username}'...")
        if not username or username == OOBE_USER or not user_exists(username):
            log(f"WARNING: Real user '{username}' is missing or invalid. Re-triggering OOBE flow.")
            state["state"] = "OOBE_PENDING"
            save_installer_state_atomic(state)
            setup_temporary_oobe_user()
            configure_lightdm_oobe()
            return 0

        # Configure LightDM for real user
        configure_lightdm_real_user(username)

        # Cleanup temporary OOBE user
        cleanup_temporary_oobe_user()

        # Ensure DESKTOP_READY is persisted
        if current_state != "DESKTOP_READY":
            state["state"] = "DESKTOP_READY"
            state["oobeCompleted"] = True
            save_installer_state_atomic(state)
            log("Transitioned state to DESKTOP_READY.")

        log("Desktop session handoff complete. System will start into normal user desktop.")
        return 0

    else:
        log(f"Notice: Unknown state '{current_state}'. Defaulting to safe no-op.")
        return 0

if __name__ == "__main__":
    ret = orchestrate_first_boot()
    sys.exit(ret)
