#!/bin/sh
#
# Installation script for picochess
#

echo "starting by updating system..."
apt update
apt full-upgrade

echo "installing needed programs"
apt install git sox unzip wget libtcl8.6 telnet libglib2.0-dev
apt install avahi-daemon avahi-discover libnss-mdns
apt install vorbis-tools
apt install python python3-pip
apt install python3-dev libffi-dev libssl-dev

if [ -d "/opt/picochess" ]; then
    echo "picochess already exists, updating code..."
    cd /opt/picochess
    git pull
else
    echo "fetching picochess..."
    cd /opt
    git clone https://github.com/JohanSjoblom/picochess
    cd picochess
    python -m venv venv
    chown -R pi /opt/picochess/logs
    ln -sf /opt/picochess/etc/dgtpicom_$(uname -m) /opt/picochess/etc/dgtpicom
    ln -sf /opt/picochess/etc/dgtpicom.$(uname -m).so /opt/picochess/etc/dgtpicom.so
fi

if [ -f "/opt/picochess/picochess.ini" ]; then
    echo "picochess.ini already existed - no changes done"
else
    cd /opt/picochess
    cp picochess.ini.example-webpi4 picochess.ini
    chown pi picochess.ini
fi

echo "checking required python modules..."
cd /opt/picochess
/opt/picochess/venv/bin/pip3 install --upgrade pip
/opt/picochess/venv/bin/pip3 install --upgrade -r requirements.txt

cp etc/dgtpi.service /etc/systemd/system/
cp etc/picochess.service /etc/systemd/system/
cp etc/obooksrv.service /etc/systemd/system/
cp etc/gamesdb.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable dgtpi.service
systemctl enable picochess.service
systemctl enable obooksrv.service
systemctl enable gamesdb.service

echo "giving bluetooth rights"
setcap 'cap_net_raw,cap_net_admin+eip' /opt/picochess/venv/lib/python3.11/site-packages/bluepy/bluepy-helper

echo "Picochess installation complete. Please reboot"
echo "After reboot open a browser to localhost:8080"
echo "Depending on your DGT hardware or only Web chose a picochess.ini-example* file"
echo "Default installation is picochess.ini-example-webpi copied to picochess.ini"
echo "In case of problems have a look in the log /opt/picochess/logs/picochess.log"
