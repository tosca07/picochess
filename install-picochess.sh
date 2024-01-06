#!/bin/sh
#
# Installation script for picochess
#

apt update
apt full-upgrade -y
apt install git sox unzip wget python3-pip libtcl8.6 telnet libglib2.0-dev -y

pip3 install --upgrade pip

cd /opt

git clone https://github.com/ghislainbourgeois/picochess

python3 -m venv /opt/picochess_venv
source /opt/picochess_venv/bin/activate

cd picochess

pip3 install --upgrade -r requirements.txt

cp etc/dgtpi.service /etc/systemd/system/
cp etc/picochess.service /etc/systemd/system/
cp etc/obooksrv.service /etc/systemd/system/
cp etc/gamesdb.service /etc/systemd/system/

systemctl daemon-reload
systemctl enable dgtpi.service
systemctl enable picochess.service
systemctl enable obooksrv.service
systemctl enable gamesdb.service

cd tablebases
./download-syzygy345.sh

echo "Picochess installation complete. Please reboot"
