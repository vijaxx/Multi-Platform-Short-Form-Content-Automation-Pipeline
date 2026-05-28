#!/bin/zsh
# Idempotent: ensure the FrameWise Chrome instance is running with
# --remote-debugging-port=9222. If already running, do nothing.
# If not running, launch it (Rumble cookies persist in the profile dir).

PROFILE_DIR="$HOME/Library/Application Support/FrameWiseChrome"
PORT=9222

# Already running?
if curl -s --max-time 2 "http://127.0.0.1:${PORT}/json/version" > /dev/null 2>&1; then
    # Ensure both Rumble + Facebook tabs exist. Chrome 127+ requires PUT for /json/new
    # (GET was deprecated). Try PUT, then fall back to kill+restart if still missing.
    TABS_JSON=$(curl -s "http://127.0.0.1:${PORT}/json" 2>/dev/null)
    NEED_RESTART=0
    if ! echo "$TABS_JSON" | grep -q "rumble.com/upload"; then
        curl -s -X PUT "http://127.0.0.1:${PORT}/json/new?https://rumble.com/upload.php" > /dev/null 2>&1
        NEED_RESTART=1
    fi
    if ! echo "$TABS_JSON" | grep -q "facebook.com"; then
        curl -s -X PUT "http://127.0.0.1:${PORT}/json/new?https://www.facebook.com/profile.php?id=61590613942018" > /dev/null 2>&1
        NEED_RESTART=1
    fi
    # Verify after PUT — if still missing, fall through to kill+restart
    if [ "$NEED_RESTART" = "1" ]; then
        sleep 2
        VERIFY=$(curl -s "http://127.0.0.1:${PORT}/json" 2>/dev/null)
        if echo "$VERIFY" | grep -q "rumble.com" && echo "$VERIFY" | grep -q "facebook.com"; then
            echo "Both tabs ensured via PUT"
            exit 0
        fi
        echo "PUT didn't take — killing Chrome to relaunch with both tabs"
        pkill -f "FrameWiseChrome.*remote-debugging-port=${PORT}"
        sleep 3
        # Fall through to launch block below
    else
        echo "Chrome already running on port ${PORT} with both tabs"
        exit 0
    fi
fi

# Make sure profile dir exists (first run only)
mkdir -p "$PROFILE_DIR"

# Launch Chrome detached, no automation flags whatsoever
# Open BOTH Rumble upload page AND FrameWise Cinema FB Page so both tabs exist for the pipeline
echo "Launching FrameWise Chrome on port ${PORT}..."
nohup "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --user-data-dir="$PROFILE_DIR" \
    --remote-debugging-port=$PORT \
    --no-first-run \
    --no-default-browser-check \
    --window-size=1280,900 \
    "https://rumble.com/upload.php" \
    "https://www.facebook.com/profile.php?id=61590613942018" \
    > "$HOME/FrameWise-Cinema/logs/chrome_framewise.log" 2>&1 &

# Wait up to 15s for debug port to come up
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    sleep 1
    if curl -s --max-time 1 "http://127.0.0.1:${PORT}/json/version" > /dev/null 2>&1; then
        echo "Chrome ready on port ${PORT} after ${i}s"
        # Give pages time to load
        sleep 3
        exit 0
    fi
done

echo "ERROR: Chrome failed to start on port ${PORT} within 15s"
exit 1
