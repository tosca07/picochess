#!/bin/bash

FLAG="/home/pi/run_picochess_update.flag"
SCRIPT="/opt/picochess/install-picochess.sh"
LOGFILE="/var/log/picochess-update.log"
TIMESTAMP_FILE="/var/log/picochess-last-update"

# Create log file if it doesn't exist
touch "$LOGFILE"
touch "$TIMESTAMP_FILE"

# Check if the flag file exists
if [ -f "$FLAG" ]; then
    # Get current and last run time
    NOW=$(date +%s)
    LAST_RUN=$(cat "$TIMESTAMP_FILE" 2>/dev/null || echo 0)
    DIFF=$((NOW - LAST_RUN))

    # One day = 86400 seconds
    if [ "$DIFF" -ge 86400 ]; then
        echo "$(date): Running PicoChess update..." | tee -a "$LOGFILE"
        
        # Clear the flag first to avoid loops
        rm "$FLAG"

        # Update timestamp
        echo "$NOW" > "$TIMESTAMP_FILE"

        # Run the update script
        bash "$SCRIPT" >> "$LOGFILE" 2>&1

        # Optionally reboot
        reboot

    else
        echo "$(date): Skipped update (last run was less than a day ago)" >> "$LOGFILE"
        rm "$FLAG"  # Optionally remove flag to prevent retry
    fi
fi
