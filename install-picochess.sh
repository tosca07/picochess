#!/bin/sh
#
# Installation script for picochess
#

# Check for the "pico" parameter, if present skip system upgrade
SKIP_UPDATE=false
if [ "$1" = "pico" ]; then
    SKIP_UPDATE=true
fi

if [ "$SKIP_UPDATE" = false ]; then
    echo "starting by upgrading system before installing picochess"
    apt update && apt upgrade -y
else
    echo "Skipping system update because 'pico' parameter was given."
    echo "Updating Picochess but not system"
fi

# BACKUP section starts
###############################################################################
# Safe Auto-Updater for Git Repository
# - Backs up working directory, including untracked files
# - Keeps latest 2 backups, deletes older ones
# - Only resets if current branch is 'main'
# - Untracked files are preserved in working directory
###############################################################################

if [ -d "/opt/picochess" ]; then
    echo "picochess already exists, creating BACKUP ..."

    # === Configuration ===
    REPO_DIR="/opt/picochess" # Path to Git repo
    BRANCH="master"           # Expected working branch
    REMOTE="origin"           # Remote to pull from
    BACKUP_ROOT="/home/pi/pico_backups"  # Where backups will be stored
    MAX_BACKUPS=2             # Number of recent backups to keep

    # === Timestamped Backup Directory ===
    TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
    BACKUP_DIR="$BACKUP_ROOT/backup_$TIMESTAMP"
    WORKING_COPY_DIR="$BACKUP_DIR/working_copy"
    UNTRACKED_DIR="$BACKUP_DIR/untracked_files"

    # Create required directories
    mkdir -p "$WORKING_COPY_DIR" "$UNTRACKED_DIR"

    echo "Creating backup in: $BACKUP_DIR"
    cd "$REPO_DIR" || exit 1

    # === Save Git diff of local changes ===
    echo "Saving git diff..."
    git diff > "$BACKUP_DIR/local_changes.diff"

    # === Save untracked files into their own subdirectory ===
    echo "Saving untracked files..."
    git ls-files --others --exclude-standard | while read -r file; do
    mkdir -p "$UNTRACKED_DIR/$(dirname "$file")"
    cp -p "$file" "$UNTRACKED_DIR/$file"
    done

    # === Copy full working directory, excluding .git ===
    echo "Copying working directory..."
    rsync -a --exclude='.git' ./ "$WORKING_COPY_DIR/"

    # === Remove older backups beyond MAX_BACKUPS ===
    echo "Cleaning up old backups..."
    ls -1dt "$BACKUP_ROOT"/backup_* 2>/dev/null | tail -n +$(($MAX_BACKUPS + 1)) | while read -r old; do
    echo "Deleting $old"
    rm -rf "$old"
    done
    echo "Update complete. Backup safely stored at: $BACKUP_DIR"
fi
#
# BACKUP section ends
#

echo " ------------------------- "
echo "installing needed libraries"
apt -y install git sox unzip wget libtcl8.6 telnet libglib2.0-dev
apt -y install avahi-daemon avahi-discover libnss-mdns
apt -y install vorbis-tools
apt -y install python3 python3-pip
apt -y install python3-dev
apt -y install python3-venv
apt -y install libffi-dev libssl-dev
apt -y install tk tcl libtcl8.6
# following line is for (building) and running leela-chess-zero
apt -y install libopenblas-dev ninja-build meson
# following line are to run mame (missing on lite images)
apt -y install libsdl2-2.0-0 libsdl2-ttf-2.0-0 qt5ct

echo " ------- "
if [ -d "/opt/picochess" ]; then
    echo "picochess already exists, updating code..."
    cd /opt
    chown -R pi /opt/picochess
    cd /opt/picochess
    # new forced backup starts
    # === Check current Git branch ===
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

    if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    echo "WARNING: You are on branch '$CURRENT_BRANCH', not '$BRANCH'."
    echo "Skipping update to avoid interfering with work on another branch."
    echo "Backup completed at: $BACKUP_DIR"
    exit 0
    fi

    # === Fetch and reset to latest remote state ===
    echo "Updating repository from $REMOTE/$BRANCH..."
    git fetch "$REMOTE"
    git reset --hard "$REMOTE/$BRANCH"
    cd /opt/picochess
    # new forced backup ends
else
    echo "fetching picochess..."
    cd /opt
    mkdir picochess
    chown pi /opt/picochess
    sudo -u pi git clone https://github.com/JohanSjoblom/picochess
    chown -R pi /opt/picochess
    cd picochess
fi

if [ -d "/opt/picochess/logs" ]; then
    echo "logs dir already exists - making sure pi is owner"
    chown -R pi /opt/picochess/logs
else
    echo "creating logs dir for pi user"
    sudo -u pi mkdir /opt/picochess/logs
fi

echo " ------- "
if [ -d "/opt/picochess/venv" ]; then
    echo "venv already exists - making sure pi is owner and group"
    chown -R pi /opt/picochess/venv
    chgrp -R pi /opt/picochess/venv
else
    echo "creating virtual Python env named venv"
    sudo -u pi python3 -m venv venv    
fi

if [ -f "/opt/picochess/picochess.ini" ]; then
    echo "picochess.ini already existed - no changes done"
else
    cd /opt/picochess
    cp picochess.ini.example-web-$(uname -m) picochess.ini
    chown pi picochess.ini
fi

# in case we dont have any engines.ini or favorites.ini
# copy in the default files - ini files should not be in repository
if [ -f "/opt/picochess/engines/aarch64/engines.ini" ]; then
    echo "aarch64 engines.ini already existed - no changes done"
else
    cd /opt/picochess
    cp engines-example-aarch64.ini /opt/picochess/engines/aarch64/engines.ini
    chown pi /opt/picochess/engines/aarch64/engines.ini
fi

if [ -f "/opt/picochess/engines/x86_64/engines.ini" ]; then
    echo "x86_64 engines.ini already existed - no changes done"
else
    cd /opt/picochess
    cp engines-example-x86_64.ini /opt/picochess/engines/x86_64/engines.ini
    chown pi /opt/picochess/engines/x86_64/engines.ini
fi

if [ -f "/opt/picochess/engines/aarch64/favorites.ini" ]; then
    echo "aarch64 favorites.ini already existed - no changes done"
else
    cd /opt/picochess
    cp favorites-example-aarch64.ini /opt/picochess/engines/aarch64/favorites.ini
    chown pi /opt/picochess/engines/aarch64/favorites.ini
fi

if [ -f "/opt/picochess/engines/x86_64/favorites.ini" ]; then
    echo "x86_64 favorites.ini already existed - no changes done"
else
    cd /opt/picochess
    cp favorites-example-x86_64.ini /opt/picochess/engines/x86_64/favorites.ini
    chown pi /opt/picochess/engines/x86_64/favorites.ini
fi

echo " ------- "
echo "checking required python modules..."
cd /opt/picochess
sudo -u pi /opt/picochess/venv/bin/pip3 install --upgrade pip
sudo -u pi /opt/picochess/venv/bin/pip3 install --upgrade -r requirements.txt

echo " ------- "
echo "setting up picochess, obooksrv, gamesdb, and update services"
cp etc/picochess.service /etc/systemd/system/
ln -sf /opt/picochess/obooksrv/$(uname -m)/obooksrv /opt/picochess/obooksrv/obooksrv
cp etc/obooksrv.service /etc/systemd/system/
ln -sf /opt/picochess/gamesdb/$(uname -m)/tcscid /opt/picochess/gamesdb/tcscid
cp etc/gamesdb.service /etc/systemd/system/
cp etc/picochess-update.service /etc/systemd/system/
cp etc/run-picochess-if-flagged.sh /usr/local/bin/
chmod +x /usr/local/bin/run-picochess-if-flagged.sh
touch /var/log/picochess-update.log /var/log/picochess-last-update
chown root:root /var/log/picochess-*
systemctl daemon-reload
systemctl enable picochess.service
systemctl enable obooksrv.service
systemctl enable gamesdb.service
systemctl enable picochess-update.service

echo " ------- "
echo "after each system update we need to rerun the cap_net rights"
echo "giving bluetooth rights so that communication works to DGT board etc"
setcap 'cap_net_raw,cap_net_admin+eip' /opt/picochess/venv/lib/python3.11/site-packages/bluepy/bluepy-helper
echo "giving rights to python to use port 80 and to shutdown and reboot"
setcap 'cap_sys_boot,cap_net_bind_service+eip' $(readlink -f $(which python3))

echo " ------- "
echo "Picochess installation complete. Please reboot"
echo "NOTE: If you are on DGTPi clock hardware you need to run install-dgtpi-clock.sh"
echo "After reboot open a browser to localhost"
echo "If you have a DGT board you need to change the board type"
echo "in the picochess.ini like this: board-type = dgt"
echo "Other board types are also supported - see the picochess.ini file"
echo " ------- "
echo "In case of problems have a look in the log /opt/picochess/logs/picochess.log"
echo "You can rerun this installation whenever you want to update your system"
echo "Use the parameter pico if you want to skip system update"
