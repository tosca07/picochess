#!/bin/sh
#
# Installation script for picochess
#

echo "starting by updating library information"
apt -y update
echo "and upgrading system before installing picochess"
apt -y full-upgrade

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
    sudo -u pi git pull
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

echo " ------- "
echo "checking required python modules..."
cd /opt/picochess
sudo -u pi /opt/picochess/venv/bin/pip3 install --upgrade pip
sudo -u pi /opt/picochess/venv/bin/pip3 install --upgrade -r requirements.txt

echo " ------- "
echo "setting up picochess, obooksrv and gamesdb services"
cp etc/picochess.service /etc/systemd/system/
ln -sf /opt/picochess/obooksrv/$(uname -m)/obooksrv /opt/picochess/obooksrv/obooksrv
cp etc/obooksrv.service /etc/systemd/system/
ln -sf /opt/picochess/gamesdb/$(uname -m)/tcscid /opt/picochess/gamesdb/tcscid
cp etc/gamesdb.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable picochess.service
systemctl enable obooksrv.service
systemctl enable gamesdb.service

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
