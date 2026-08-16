#!/usr/bin/env bash
# Windroid OS Desktop Shell Watchdog Runner
# Automatically restarts Windroid Shell if it crashes or terminates unexpectedly.

export DISPLAY="${DISPLAY:-:0}"

SHELL_LOG="/tmp/windroid-shell.log"
HTTP_LOG="/tmp/windroid-http.log"
CHROMIUM_LOG="/tmp/windroid-chromium.log"
BRIDGE_LOG="/tmp/windroid-bridge.log"

echo "[Windroid OS] Initializing Desktop Shell Watchdog at $(date)" > "$SHELL_LOG"

# Authoritative runtime mode & state detection
CMDLINE=$(cat /proc/cmdline 2>/dev/null || echo "")
RUNTIME_MODE="installed"
if [ -f "/etc/windroid/runtime-mode" ]; then
    RUNTIME_MODE=$(cat /etc/windroid/runtime-mode | tr -d ' \n\r')
elif [ -d "/run/live" ] || [ -d "/run/live/medium" ] || [ -d "/cdrom" ] || echo "$CMDLINE" | grep -q "boot=live"; then
    RUNTIME_MODE="live"
fi

NATIVE_STATE="NOT_INSTALLED"
if [ -f "/var/lib/windroid/installer-state.json" ]; then
    NATIVE_STATE=$(python3 -c "import json; data=json.load(open('/var/lib/windroid/installer-state.json')); print(data.get('state', 'UNKNOWN'))" 2>/dev/null || echo "UNKNOWN")
fi

IS_INSTALLER_BOOT=0
IS_OOBE_BOOT=0
IS_INSTALLED_DESKTOP=0

if [ "$RUNTIME_MODE" = "installed" ] || [ "$NATIVE_STATE" = "OOBE_PENDING" ] || [ "$NATIVE_STATE" = "OOBE_IN_PROGRESS" ] || [ "$NATIVE_STATE" = "OOBE_COMPLETE" ] || [ "$NATIVE_STATE" = "DESKTOP_READY" ]; then
    if [ "$NATIVE_STATE" = "OOBE_PENDING" ] || [ "$NATIVE_STATE" = "OOBE_IN_PROGRESS" ]; then
        IS_OOBE_BOOT=1
        echo "[Windroid OS] INSTALLED BOOT: Native state is '${NATIVE_STATE}'. Launching Windroid OOBE Session..." >> "$SHELL_LOG"
    else
        IS_INSTALLED_DESKTOP=1
        echo "[Windroid OS] INSTALLED BOOT: Native state is '${NATIVE_STATE}'. Launching Windroid User Desktop..." >> "$SHELL_LOG"
    fi
elif [ "$RUNTIME_MODE" = "live" ] && echo "$CMDLINE" | grep -q "windroid.mode=installer"; then
    IS_INSTALLER_BOOT=1
    echo "[Windroid OS] LIVE ISO BOOT: Kernel cmdline contains 'windroid.mode=installer'. Launching DEDICATED LIVE INSTALLER SESSION..." >> "$SHELL_LOG"
else
    echo "[Windroid OS] LIVE ISO BOOT: Launching FULL WINDROID LIVE DESKTOP..." >> "$SHELL_LOG"
fi

HTTP_PID=""
BRIDGE_PID=""

cleanup() {
    echo "[Windroid OS] Runner shutting down, performing cleanup..." >> "$SHELL_LOG"
    if [ -n "$HTTP_PID" ] && kill -0 "$HTTP_PID" 2>/dev/null; then
        echo "[Windroid OS] Terminating HTTP server (PID $HTTP_PID)..." >> "$SHELL_LOG"
        kill "$HTTP_PID" 2>/dev/null || true
        wait "$HTTP_PID" 2>/dev/null || true
    fi
    if [ -n "$BRIDGE_PID" ] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
        echo "[Windroid OS] Terminating System Bridge (PID $BRIDGE_PID)..." >> "$SHELL_LOG"
        kill "$BRIDGE_PID" 2>/dev/null || true
        wait "$BRIDGE_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

while true; do
    if [ -x "/usr/bin/windroid-desktop" ] && [ "$IS_INSTALLER_BOOT" -eq 0 ]; then
        echo "[Windroid OS] Starting native Windroid OS Desktop Shell..." >> "$SHELL_LOG"
        /usr/bin/windroid-desktop --fullscreen >> "$SHELL_LOG" 2>&1
        EXIT_CODE=$?
    elif [ -f "/opt/windroid/web/index.html" ] || [ -f "/usr/share/windroid/web/index.html" ] || [ -f "/opt/aether-os/web/index.html" ]; then
        WEB_DIR="/opt/windroid/web"
        if [ ! -f "${WEB_DIR}/index.html" ]; then
            if [ -f "/usr/share/windroid/web/index.html" ]; then
                WEB_DIR="/usr/share/windroid/web"
            else
                WEB_DIR="/opt/aether-os/web"
            fi
        fi

        echo "[Windroid OS] Selected web bundle directory: ${WEB_DIR}" >> "$SHELL_LOG"

        if command -v python3 >/dev/null 2>&1 && command -v chromium >/dev/null 2>&1; then
            # Clean temporary profile if necessary
            rm -rf /tmp/windroid-chromium-profile 2>/dev/null || true

            # Verify Native System Bridge on 127.0.0.1:4174 (Managed by systemd windroid-bridge.service)
            echo "[Windroid OS] Verifying Native System Bridge on 127.0.0.1:4174..." >> "$SHELL_LOG"
            BRIDGE_READY=0
            for i in $(seq 1 10); do
                if command -v systemctl >/dev/null 2>&1; then
                    if ! systemctl is-active --quiet windroid-bridge.service 2>/dev/null; then
                        echo "[Windroid OS] windroid-bridge.service is not active; requesting systemctl start..." >> "$SHELL_LOG"
                        systemctl start windroid-bridge.service 2>/dev/null || true
                    fi
                fi

                if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4174/api/health')" >/dev/null 2>&1; then
                    BRIDGE_READY=1
                    break
                elif command -v curl >/dev/null 2>&1 && curl -s -f http://127.0.0.1:4174/api/health >/dev/null 2>&1; then
                    BRIDGE_READY=1
                    break
                fi
                sleep 1
            done

            if [ "$BRIDGE_READY" -eq 1 ]; then
                echo "[Windroid OS] Native System Bridge is ready at http://127.0.0.1:4174/" >> "$SHELL_LOG"
            else
                echo "[ERROR] System Bridge did not respond on 127.0.0.1:4174 within 10s!" >> "$SHELL_LOG"
                if [ "$IS_INSTALLER_BOOT" -eq 1 ]; then
                    echo "[FATAL] Native Bridge unreachable in Installer Boot Mode. Hard stopping installer session." >> "$SHELL_LOG"
                    if command -v zenity >/dev/null 2>&1; then
                        zenity --question \
                            --title="Windroid Setup - Fatal System Bridge Failure" \
                            --text="FATAL: Windroid System Bridge service (windroid-bridge.service) failed to respond on 127.0.0.1:4174.\n\nWindroid Setup cannot proceed safely without native system bridge access.\n\nWhat would you like to do?" \
                            --ok-label="Restart System" \
                            --cancel-label="Power Off" \
                            --width=420

                        FATAL_CHOICE=$?
                        if [ $FATAL_CHOICE -eq 0 ]; then
                            echo "[Windroid OS] Rebooting system..." >> "$SHELL_LOG"
                            systemctl reboot 2>/dev/null || reboot 2>/dev/null || true
                        else
                            echo "[Windroid OS] Powering off system..." >> "$SHELL_LOG"
                            systemctl poweroff 2>/dev/null || poweroff 2>/dev/null || true
                        fi
                    else
                        echo "FATAL: Native bridge unreachable in Installer mode. Powering off..." >> "$SHELL_LOG"
                        systemctl poweroff 2>/dev/null || poweroff 2>/dev/null || true
                    fi
                    # FAIL-CLOSED: Stop script immediately. Never launch HTTP server or Chromium or Live Desktop.
                    exit 1
                fi
            fi

            echo "[Windroid OS] Starting local HTTP server on port 4173..." >> "$SHELL_LOG"
            python3 -m http.server 4173 --bind 127.0.0.1 --directory "${WEB_DIR}" > "$HTTP_LOG" 2>&1 &
            HTTP_PID=$!
            echo "[Windroid OS] HTTP server launched with PID ${HTTP_PID}" >> "$SHELL_LOG"

            # Wait for server readiness (max 10s)
            SERVER_READY=0
            for i in $(seq 1 10); do
                if command -v curl >/dev/null 2>&1; then
                    if curl -s -f http://127.0.0.1:4173/ >/dev/null 2>&1; then
                        SERVER_READY=1
                        break
                    fi
                else
                    if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4173/')" >/dev/null 2>&1; then
                        SERVER_READY=1
                        break
                    fi
                fi
                sleep 1
            done

            if [ "$SERVER_READY" -eq 1 ]; then
                echo "[Windroid OS] Local HTTP server is ready at http://127.0.0.1:4173/" >> "$SHELL_LOG"
            else
                echo "[WARNING] HTTP server did not respond within 10s, proceeding with Chromium startup..." >> "$SHELL_LOG"
            fi

            CHROMIUM_BIN="$(command -v chromium)"
            echo "[Windroid OS] Starting Chromium Kiosk Web Shell using ${CHROMIUM_BIN}..." >> "$SHELL_LOG"
            
            TARGET_URL="http://127.0.0.1:4173/"
            if [ "$IS_INSTALLER_BOOT" -eq 1 ]; then
                TARGET_URL="http://127.0.0.1:4173/?mode=installer&context=boot"
                echo "[Windroid OS] Dedicated Live Installer URL: ${TARGET_URL}" >> "$SHELL_LOG"
            elif [ "$IS_OOBE_BOOT" -eq 1 ]; then
                TARGET_URL="http://127.0.0.1:4173/?mode=oobe&context=installed-boot"
                echo "[Windroid OS] Dedicated Installed OOBE URL: ${TARGET_URL}" >> "$SHELL_LOG"
            elif [ "$IS_INSTALLED_DESKTOP" -eq 1 ]; then
                TARGET_URL="http://127.0.0.1:4173/?mode=installed&context=boot"
                echo "[Windroid OS] Dedicated Installed Desktop URL: ${TARGET_URL}" >> "$SHELL_LOG"
            else
                TARGET_URL="http://127.0.0.1:4173/?mode=live&context=live-desktop"
                echo "[Windroid OS] Dedicated Live Desktop URL: ${TARGET_URL}" >> "$SHELL_LOG"
            fi

            "$CHROMIUM_BIN" \
                --kiosk \
                --no-first-run \
                --disable-session-crashed-bubble \
                --disable-infobars \
                --disable-background-networking \
                --disable-component-update \
                --disable-sync \
                --disable-translate \
                --password-store=basic \
                --user-data-dir=/tmp/windroid-chromium-profile \
                "$TARGET_URL" >> "$CHROMIUM_LOG" 2>&1
            
            EXIT_CODE=$?
            echo "[Windroid OS] Chromium exited with code $EXIT_CODE" >> "$SHELL_LOG"

            # Terminate HTTP server for this session iteration
            if [ -n "$HTTP_PID" ] && kill -0 "$HTTP_PID" 2>/dev/null; then
                echo "[Windroid OS] Stopping HTTP server PID $HTTP_PID..." >> "$SHELL_LOG"
                kill "$HTTP_PID" 2>/dev/null || true
                wait "$HTTP_PID" 2>/dev/null || true
                HTTP_PID=""
            fi
            if [ -n "$BRIDGE_PID" ] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
                echo "[Windroid OS] Stopping System Bridge PID $BRIDGE_PID..." >> "$SHELL_LOG"
                kill "$BRIDGE_PID" 2>/dev/null || true
                wait "$BRIDGE_PID" 2>/dev/null || true
                BRIDGE_PID=""
            fi
        elif [ "$IS_INSTALLER_BOOT" -eq 1 ]; then
            echo "[FATAL] Chromium binary is missing; required for Installer Boot Mode." >> "$SHELL_LOG"
            EXIT_CODE=1
        elif command -v firefox >/dev/null 2>&1; then
            echo "[Windroid OS] Starting Firefox Kiosk Web Shell..." >> "$SHELL_LOG"
            TARGET_URL="file://${WEB_DIR}/index.html"
            firefox --kiosk "$TARGET_URL" >> "$CHROMIUM_LOG" 2>&1
            EXIT_CODE=$?
        else
            echo "[Windroid OS] Missing python3 or chromium executable." >> "$SHELL_LOG"
            EXIT_CODE=1
        fi
    else
        echo "[Windroid OS] Desktop Shell executable or web bundle not found." >> "$SHELL_LOG"
        EXIT_CODE=1
    fi

    echo "[Windroid OS] Desktop Shell loop iteration finished with exit code $EXIT_CODE" >> "$SHELL_LOG"

    # In Installer Boot Mode, exiting shell must NEVER drop to Live Desktop
    if [ "$IS_INSTALLER_BOOT" -eq 1 ]; then
        echo "[Windroid OS] Installer session closed. Triggering exit options..." >> "$SHELL_LOG"
        if command -v zenity >/dev/null 2>&1; then
            zenity --question \
                --title="Exit Windroid Setup" \
                --text="Windroid OS Setup has exited.\n\nChoose an action to proceed:" \
                --ok-label="Power Off" \
                --cancel-label="Restart Setup" \
                --width=380

            EXIT_DECISION=$?
            if [ $EXIT_DECISION -eq 0 ]; then
                echo "[Windroid OS] Powering off system after installer exit..." >> "$SHELL_LOG"
                systemctl poweroff 2>/dev/null || poweroff 2>/dev/null || true
                break
            fi
        else
            sleep 2
        fi
    else
        # Live Mode interactive restart dialog
        if command -v zenity >/dev/null 2>&1; then
            zenity --question \
                --title="Windroid OS Desktop" \
                --text="Windroid OS Desktop Shell has stopped.\n\nWould you like to restart the session?" \
                --ok-label="Restart Shell" \
                --cancel-label="Exit Session" \
                --width=360 \
                --timeout=15

            RESTART_DECISION=$?
            if [ $RESTART_DECISION -ne 0 ]; then
                echo "[Windroid OS] Session termination requested by user." >> "$SHELL_LOG"
                break
            fi
        else
            sleep 3
        fi
    fi
done

