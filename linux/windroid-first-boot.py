#!/usr/bin/env python3
"""
Windroid OS First-Boot Service Orchestrator
Runs before lightdm.service / display-manager.service on boot.
Reads /var/lib/windroid/installer-state.json and enforces system session state:
- OOBE_PENDING / OOBE_IN_PROGRESS:
    Configures system for temporary unprivileged 'windroid-oobe' session.
    Forces LightDM autologin to 'windroid-oobe' into Openbox.
    Ensures OOBE shell starts without displaying any login prompts.
- OOBE_COMPLETE / DESKTOP_READY:
    Ensures autologin/session is configured for the registered user.
    Cleans up any temporary OOBE user session.
- FAILED / INSTALLER / INSTALLATION_IN_PROGRESS:
    Preserves installer recovery path. Does NOT start OOBE session or create windroid-oobe.
"""

import os
import sys
import json
import pwd
import subprocess
import datetime

STATE_FILE = "/var/lib/windroid/installer-state.json"
LIGHTDM_CONF = "/etc/lightdm/lightdm.conf.d/80-windroid-autologin.conf"

def log(msg):
    print(f"[windroid-first-boot] {msg}", flush=True)

def run_cmd(cmd):
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        return res.returncode == 0, res.stdout, res.stderr
    except Exception as e:
        return False, "", str(e)

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"state": "NOT_INSTALLED"}
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        log(f"Error reading state file {STATE_FILE}: {e}")
        return {"state": "FAILED", "error": str(e)}

def save_state_in_progress(state_data):
    try:
        state_data["state"] = "OOBE_IN_PROGRESS"
        state_data["updatedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        state_data["installationCompleted"] = True
        state_data["oobeCompleted"] = False
        dirpath = os.path.dirname(STATE_FILE)
        os.makedirs(dirpath, exist_ok=True)
        tmppath = STATE_FILE + ".tmp"
        with open(tmppath, "w") as f:
            json.dump(state_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmppath, STATE_FILE)
        try:
            dfd = os.open(dirpath, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except Exception:
            pass
    except Exception as e:
        log(f"Warning: Could not save OOBE_IN_PROGRESS state: {e}")

def ensure_oobe_user_session():
    log("Setting up temporary 'windroid-oobe' session for Phase 2 OOBE...")
    
    user_exists = False
    try:
        pwd.getpwnam("windroid-oobe")
        user_exists = True
    except KeyError:
        pass

    if not user_exists:
        log("Creating temporary 'windroid-oobe' system account...")
        ok, out, err = run_cmd(["useradd", "-r", "-m", "-c", "Windroid OOBE Setup", "-s", "/bin/bash", "windroid-oobe"])
        if not ok and "already exists" not in err:
            log(f"Warning: useradd windroid-oobe returned error: {err}")

    oobe_home = "/home/windroid-oobe"
    if os.path.exists(oobe_home):
        openbox_dir = f"{oobe_home}/.config/openbox"
        os.makedirs(openbox_dir, exist_ok=True)
        autostart_path = f"{openbox_dir}/autostart"
        with open(autostart_path, "w") as f:
            f.write("#!/bin/sh\n/usr/bin/windroid-shell-runner.sh &\n")
        os.chmod(autostart_path, 0o755)
        run_cmd(["chown", "-R", "windroid-oobe:windroid-oobe", oobe_home])

    os.makedirs("/etc/lightdm/lightdm.conf.d", exist_ok=True)
    conf_lines = [
        "[Seat:*]\n",
        "autologin-guest=false\n",
        "autologin-user=windroid-oobe\n",
        "autologin-user-timeout=0\n",
        "user-session=openbox\n"
    ]
    with open(LIGHTDM_CONF, "w") as f:
        f.writelines(conf_lines)
    log(f"Configured {LIGHTDM_CONF} for autologin-user=windroid-oobe")

def main():
    log("Initializing Windroid First-Boot Orchestrator...")
    state_data = load_state()
    current_state = state_data.get("state", "UNKNOWN")
    log(f"Loaded persistent native state: '{current_state}'")

    if current_state in ["OOBE_PENDING", "OOBE_IN_PROGRESS"]:
        ensure_oobe_user_session()
        if current_state == "OOBE_PENDING":
            save_state_in_progress(state_data)
    elif current_state in ["OOBE_COMPLETE", "DESKTOP_READY"]:
        u_cfg = state_data.get("userConfig") or {}
        username = u_cfg.get("username", "").strip()
        if username and username != "windroid-oobe":
            try:
                pwd.getpwnam(username)
                log(f"Target user account '{username}' confirmed present. Ensuring LightDM autologin...")
                os.makedirs("/etc/lightdm/lightdm.conf.d", exist_ok=True)
                conf_lines = [
                    "[Seat:*]\n",
                    "autologin-guest=false\n",
                    f"autologin-user={username}\n",
                    "autologin-user-timeout=0\n",
                    "user-session=openbox\n"
                ]
                with open(LIGHTDM_CONF, "w") as f:
                    f.writelines(conf_lines)
            except KeyError:
                log(f"User '{username}' from state not found in system! Falling back to OOBE session.")
                ensure_oobe_user_session()
        else:
            log("No valid username found in DESKTOP_READY state! Falling back to OOBE session.")
            ensure_oobe_user_session()

        try:
            pwd.getpwnam("windroid-oobe")
            log("Removing temporary 'windroid-oobe' system account...")
            run_cmd(["userdel", "-r", "windroid-oobe"])
        except KeyError:
            pass
    elif current_state in ["FAILED", "INSTALLER", "INSTALLATION_IN_PROGRESS"]:
        log(f"Installation state is '{current_state}'. Not starting OOBE session. Preserving installer recovery mode.")
        # Ensure temporary OOBE user is NOT configured or used
        try:
            pwd.getpwnam("windroid-oobe")
            log("Cleaning up temporary 'windroid-oobe' system account...")
            run_cmd(["userdel", "-r", "windroid-oobe"])
        except KeyError:
            pass
    else:
        log(f"Unrecognized state '{current_state}', maintaining default system boot state.")

if __name__ == "__main__":
    main()
