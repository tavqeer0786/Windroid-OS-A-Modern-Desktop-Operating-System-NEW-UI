#!/usr/bin/env python3
"""
Windroid OS Installed First-Boot & OOBE Orchestrator
Production-Grade Boot-Chain Implementation (Phase 2B Hardened)

This service runs as root early before display-manager/lightdm on the INSTALLED system.
It is responsible for:
1. Verifying that execution is on the installed root filesystem (not Live ISO).
2. Authoritatively reading /var/lib/windroid/installer-state.json.
3. Orchestrating temporary unprivileged 'windroid-oobe' user & LightDM for OOBE.
4. Orchestrating real-user LightDM transition and temporary user cleanup on completion.
5. Guaranteeing idempotency and preventing any return to the Phase-1 installer.
6. Failing closed if installation state is incomplete, corrupt, failed, or unauthorized.
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

STATE_VERSION = "windroid-installer-state-v1"

VALID_STATES = [
    "INSTALLER",
    "INSTALLATION_IN_PROGRESS",
    "INSTALLATION_COMPLETE",
    "OOBE_PENDING",
    "OOBE_IN_PROGRESS",
    "OOBE_COMPLETE",
    "DESKTOP_READY",
    "FAILED"
]

RESERVED_SYSTEM_USERNAMES = {
    "root", "bin", "daemon", "sys", "sync", "games", "man", "lp", "mail", "news",
    "uucp", "proxy", "www-data", "backup", "list", "irc", "gnats", "nobody",
    "systemd-network", "systemd-resolve", "messagebus", "systemd-timesync",
    "avahi-autoipd", "avahi", "usbmux", "dnsmasq", "kdm", "gdm", "lightdm",
    "nodm", "desktop", "guest", "live", "user", "windroid-pc", "windroid-oobe"
}

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

def validate_state(data: dict) -> tuple[bool, str | None]:
    """Validates state data invariants strictly."""
    if not isinstance(data, dict):
        return False, "State data must be a dictionary"

    if data.get("version") != STATE_VERSION:
        return False, f"Invalid version: '{data.get('version')}', expected '{STATE_VERSION}'"

    state = data.get("state")
    if state not in VALID_STATES:
        return False, f"Invalid state: '{state}'"

    if state == "INSTALLER":
        if data.get("installationCompleted") is True:
            return False, "installationCompleted must be false for INSTALLER"
        if data.get("oobeCompleted") is True:
            return False, "oobeCompleted must be false for INSTALLER"
        return True, None

    if state == "INSTALLATION_IN_PROGRESS":
        if data.get("userConfig") is not None:
            return False, "userConfig must be null during INSTALLATION_IN_PROGRESS"
        if data.get("installationCompleted") is True:
            return False, "installationCompleted must be false during INSTALLATION_IN_PROGRESS"
        if data.get("oobeCompleted") is True:
            return False, "oobeCompleted must be false during INSTALLATION_IN_PROGRESS"
        return True, None

    if state == "OOBE_PENDING":
        if data.get("userConfig") is not None:
            return False, "userConfig must be null in OOBE_PENDING state before user registration"
        if data.get("installationCompleted") is not True:
            return False, "installationCompleted must be true for OOBE_PENDING"
        if data.get("oobeCompleted") is True:
            return False, "oobeCompleted must be false for OOBE_PENDING"
        if not (data.get("installationCompletedAt") or data.get("completedAt") or data.get("updatedAt")):
            return False, "Timestamp (installationCompletedAt) must be present for OOBE_PENDING"
        if data.get("error") is not None:
            return False, "error must be null for OOBE_PENDING"
        return True, None

    if state == "OOBE_IN_PROGRESS":
        if data.get("installationCompleted") is not True:
            return False, "installationCompleted must be true for OOBE_IN_PROGRESS"
        if data.get("oobeCompleted") is True:
            return False, "oobeCompleted must be false during OOBE_IN_PROGRESS"
        if data.get("error") is not None:
            return False, "error must be null for OOBE_IN_PROGRESS"
        return True, None

    if state in ["OOBE_COMPLETE", "DESKTOP_READY"]:
        if data.get("installationCompleted") is not True:
            return False, f"installationCompleted must be true for {state}"
        if data.get("oobeCompleted") is not True:
            return False, f"oobeCompleted must be true for {state}"
        u_cfg = data.get("userConfig")
        if not isinstance(u_cfg, dict):
            return False, f"userConfig must be a valid dictionary for {state}"
        username = str(u_cfg.get("username", "")).strip()
        if not username or username == OOBE_USER or username in RESERVED_SYSTEM_USERNAMES:
            return False, f"userConfig contains invalid or reserved username: '{username}'"
        if not re.match(r'^[a-z_][a-z0-9_-]*$', username):
            return False, f"userConfig username '{username}' does not match required format"
        if not (data.get("oobeCompletedAt") or data.get("completedAt") or data.get("updatedAt")):
            return False, f"Timestamp (oobeCompletedAt) must be present for {state}"
        if data.get("error") is not None:
            return False, f"error must be null for {state}"
        return True, None

    if state == "FAILED":
        return True, None

    return True, None

def load_installer_state(state_file_path: str = STATE_FILE) -> dict:
    """
    Safely loads authoritative installer state.
    Primary state file is /var/lib/windroid/installer-state.json.
    Backup is checked ONLY if primary is absent or invalid, and backup must validate independently.
    """
    # 1. Try Primary
    if os.path.exists(state_file_path):
        try:
            with open(state_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                valid, err = validate_state(data)
                if valid:
                    return data
                else:
                    log(f"Warning: Primary state file {state_file_path} failed validation: {err}")
        except Exception as e:
            log(f"Warning: Failed to parse primary state file {state_file_path}: {e}")

    # 2. Try Backup only if primary failed/missing
    if os.path.exists(STATE_BACKUP_FILE) and STATE_BACKUP_FILE != state_file_path:
        try:
            with open(STATE_BACKUP_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                valid, err = validate_state(data)
                if valid:
                    log(f"Recovery: Primary state missing/corrupt, successfully recovered valid state from backup {STATE_BACKUP_FILE} (state: {data.get('state')})")
                    return data
                else:
                    log(f"Warning: Backup state file {STATE_BACKUP_FILE} also failed validation: {err}")
        except Exception as e:
            log(f"Warning: Failed to parse backup state file {STATE_BACKUP_FILE}: {e}")

    # 3. Fail closed if neither primary nor backup is valid
    log("Error: Neither primary nor backup installer-state is valid. Returning fail-closed state.")
    return {
        "version": STATE_VERSION,
        "state": "FAILED",
        "installationCompleted": False,
        "oobeCompleted": False,
        "error": "Installer state file missing or corrupt"
    }

def save_installer_state_atomic(state_data: dict, target_root: str = "/") -> bool:
    """Persists installer state using strict atomic write semantics."""
    valid, err = validate_state(state_data)
    if not valid:
        log(f"ERROR: Refusing to save invalid state data: {err}")
        return False

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
    """Idempotently creates unprivileged temporary windroid-oobe user with minimal GUI groups and no sudo."""
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

        # Set empty/unlocked password status for GUI login
        run_cmd(["passwd", "-d", OOBE_USER])

    # Assign ONLY minimal GUI groups (strictly NO sudo)
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

def clear_all_autologin_configs():
    """Removes all Windroid autologin configurations to prevent invalid autologin sessions."""
    for cfg in [LIGHTDM_OOBE_CONF, LIGHTDM_AUTOLOGIN_CONF, LIGHTDM_LIVE_CONF]:
        if os.path.exists(cfg):
            try:
                os.remove(cfg)
                log(f"Cleared autologin config: {cfg}")
            except Exception as e:
                log(f"Notice: Failed to remove {cfg}: {e}")

def configure_lightdm_oobe() -> bool:
    """Configures LightDM for temporary windroid-oobe graphical session using write -> validate -> replace."""
    os.makedirs(LIGHTDM_CONF_DIR, exist_ok=True)
    tmp_path = os.path.join(LIGHTDM_CONF_DIR, "80-windroid-oobe.conf.tmp")
    target_path = LIGHTDM_OOBE_CONF

    conf_content = (
        "# Windroid OS OOBE Session Configuration\n"
        "[Seat:*]\n"
        "autologin-guest=false\n"
        f"autologin-user={OOBE_USER}\n"
        "autologin-user-timeout=0\n"
        "user-session=openbox\n"
    )

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(conf_content)
            f.flush()
            os.fsync(f.fileno())

        # Validate temporary file
        with open(tmp_path, "r", encoding="utf-8") as f:
            read_back = f.read()
            if f"autologin-user={OOBE_USER}" not in read_back:
                raise RuntimeError("Validation of LightDM OOBE configuration failed.")

        os.replace(tmp_path, target_path)

        # Remove conflicting autologin configs
        for old_cfg in [LIGHTDM_AUTOLOGIN_CONF, LIGHTDM_LIVE_CONF]:
            if os.path.exists(old_cfg):
                try:
                    os.remove(old_cfg)
                except Exception:
                    pass

        log(f"LightDM OOBE configuration written and validated: {target_path} (autologin-user={OOBE_USER})")
        return True
    except Exception as e:
        log(f"Error configuring LightDM for OOBE: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False

def configure_lightdm_real_user(username: str) -> bool:
    """Configures LightDM for authenticated real user session using write -> validate -> replace."""
    if not username or username == OOBE_USER or username in ["root", "user"] or username in RESERVED_SYSTEM_USERNAMES:
        log(f"Error: Refusing to configure LightDM for invalid or temporary username: '{username}'")
        return False

    os.makedirs(LIGHTDM_CONF_DIR, exist_ok=True)
    tmp_path = os.path.join(LIGHTDM_CONF_DIR, "80-windroid-autologin.conf.tmp")
    target_path = LIGHTDM_AUTOLOGIN_CONF

    conf_content = (
        f"# Windroid OS Authenticated User Session Configuration\n"
        "[Seat:*]\n"
        "autologin-guest=false\n"
        f"autologin-user={username}\n"
        "autologin-user-timeout=0\n"
        "user-session=openbox\n"
    )

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(conf_content)
            f.flush()
            os.fsync(f.fileno())

        # Validate
        with open(tmp_path, "r", encoding="utf-8") as f:
            read_back = f.read()
            if f"autologin-user={username}" not in read_back:
                raise RuntimeError(f"Validation of LightDM real user configuration failed for '{username}'.")

        os.replace(tmp_path, target_path)

        # Clean up OOBE & Live configs
        for old_cfg in [LIGHTDM_OOBE_CONF, LIGHTDM_LIVE_CONF]:
            if os.path.exists(old_cfg):
                try:
                    os.remove(old_cfg)
                except Exception:
                    pass

        log(f"LightDM Real User configuration written and validated: {target_path} (autologin-user={username})")
        return True
    except Exception as e:
        log(f"Error configuring LightDM for real user: {e}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False

def cleanup_temporary_oobe_user(real_username: str) -> bool:
    """
    Safely removes temporary windroid-oobe account ONLY after strict real-user verification.
    Required pre-conditions:
    1. real_username is valid
    2. getent passwd <real_username> succeeds
    3. real_username != root
    4. real_username != windroid-oobe
    5. real user home directory exists
    6. LightDM real-user configuration is successfully written
    """
    if not real_username or real_username in ["root", "user", OOBE_USER] or real_username in RESERVED_SYSTEM_USERNAMES:
        log(f"Pre-condition failed: real username '{real_username}' is invalid/reserved.")
        return False

    if not user_exists(real_username):
        log(f"Pre-condition failed: real user '{real_username}' does not exist in passwd database.")
        return False

    user_home = f"/home/{real_username}"
    if not os.path.exists(user_home):
        log(f"Pre-condition failed: home directory '{user_home}' does not exist.")
        return False

    if not os.path.exists(LIGHTDM_AUTOLOGIN_CONF):
        log(f"Pre-condition failed: LightDM real user config '{LIGHTDM_AUTOLOGIN_CONF}' does not exist.")
        return False

    with open(LIGHTDM_AUTOLOGIN_CONF, "r", encoding="utf-8") as f:
        if f"autologin-user={real_username}" not in f.read():
            log(f"Pre-condition failed: LightDM autologin is not set to '{real_username}'.")
            return False

    if not user_exists(OOBE_USER):
        log(f"Temporary user '{OOBE_USER}' is already absent.")
        return True

    log(f"All 6 pre-conditions verified. Safely removing temporary user account '{OOBE_USER}'...")
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

def orchestrate_first_boot() -> int:
    """
    Main orchestration entry point.
    Strictly fail-closed: returns 0 on success, 1 on failure.
    """
    log("==================================================")
    log("WINDROID OS FIRST-BOOT ORCHESTRATOR STARTING")
    log("==================================================")

    # 1. Guard against running on Live ISO
    if is_live_environment():
        log("Execution detected on LIVE ISO environment. First-boot orchestrator exiting cleanly.")
        return 0

    # 2. Load Authoritative State
    state = load_installer_state()
    current_state = state.get("state", "FAILED")
    log(f"Authoritative installer state: {current_state}")

    # 3. Fail-Closed on Incomplete, Corrupt, or Failed state
    if current_state in ["INSTALLATION_IN_PROGRESS", "FAILED", "INSTALLER"]:
        log(f"ERROR: Cannot boot graphical session in state '{current_state}'. Clearing autologin and failing closed.")
        clear_all_autologin_configs()
        return 1

    # 4. Handle OOBE_PENDING / OOBE_IN_PROGRESS
    elif current_state in ["OOBE_PENDING", "OOBE_IN_PROGRESS"]:
        log(f"Handling state '{current_state}': Preparing temporary OOBE session.")

        # Ensure runtime-mode is 'installed'
        os.makedirs("/etc/windroid", exist_ok=True)
        with open(RUNTIME_MODE_FILE, "w", encoding="utf-8") as f:
            f.write("installed\n")

        # Ensure temporary OOBE user exists
        if not setup_temporary_oobe_user():
            log("FATAL: Could not prepare temporary OOBE user. Failing closed.")
            clear_all_autologin_configs()
            return 1

        # Configure LightDM for OOBE
        if not configure_lightdm_oobe():
            log("FATAL: Could not configure LightDM for OOBE. Failing closed.")
            clear_all_autologin_configs()
            return 1

        # Update state to OOBE_IN_PROGRESS if it was OOBE_PENDING
        if current_state == "OOBE_PENDING":
            state["state"] = "OOBE_IN_PROGRESS"
            save_installer_state_atomic(state)
            log("Transitioned state to OOBE_IN_PROGRESS.")

        log("OOBE preparation complete. Ready for LightDM graphical session.")
        return 0

    # 5. Handle OOBE_COMPLETE / DESKTOP_READY
    elif current_state in ["OOBE_COMPLETE", "DESKTOP_READY"]:
        user_config = state.get("userConfig") or {}
        username = user_config.get("username", "")

        log(f"Handling state '{current_state}': Verifying real user '{username}'...")
        if not username or username == OOBE_USER or username in RESERVED_SYSTEM_USERNAMES or not user_exists(username):
            log(f"WARNING: Real user '{username}' is missing or invalid. Re-triggering OOBE flow.")
            state["state"] = "OOBE_PENDING"
            state["userConfig"] = None
            state["oobeCompleted"] = False
            save_installer_state_atomic(state)
            setup_temporary_oobe_user()
            configure_lightdm_oobe()
            return 0

        # Ensure runtime-mode is 'installed'
        os.makedirs("/etc/windroid", exist_ok=True)
        with open(RUNTIME_MODE_FILE, "w", encoding="utf-8") as f:
            f.write("installed\n")

        # Configure LightDM for real user
        if not configure_lightdm_real_user(username):
            log(f"FATAL: Could not configure LightDM for real user '{username}'.")
            clear_all_autologin_configs()
            return 1

        # Cleanup temporary OOBE user (with 6 strict pre-conditions)
        cleanup_temporary_oobe_user(username)

        # Ensure DESKTOP_READY is persisted
        if current_state != "DESKTOP_READY":
            state["state"] = "DESKTOP_READY"
            state["oobeCompleted"] = True
            save_installer_state_atomic(state)
            log("Transitioned state to DESKTOP_READY.")

        log("Desktop session handoff complete. System will start into normal user desktop.")
        return 0

    # 6. Unknown state -> Fail closed
    else:
        log(f"ERROR: Unknown state '{current_state}'. Clearing autologin and failing closed.")
        clear_all_autologin_configs()
        return 1

if __name__ == "__main__":
    ret = orchestrate_first_boot()
    sys.exit(ret)
