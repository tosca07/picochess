#!/bin/sh
#
# Installation script for DGTPi clock and DGT3000 mod
# Run install-picochess first to install base picochess
#
# you also need to set dgtpi = True in ini file - use with care, know what you are doing
# you can use the example ini file picochess.ini.example-dgtpi3-clock
echo "setting up dgtpi service for hardwired clock like DGTPi"
ln -sf /opt/picochess/etc/$(uname -m)/dgtpicom /opt/picochess/etc/dgtpicom
ln -sf /opt/picochess/etc/$(uname -m)/dgtpicom.so /opt/picochess/etc/dgtpicom.so
cp etc/dgtpi.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable dgtpi.service

echo "no setcap rights used in this script, they are all in install-dgtpi-clock.sh"
echo "setcap not needed as no system update done here"

echo " ------- "
echo "DGTPi clock installation complete. Please reboot"
echo "You need to copy picochess.ini-example-dgtpi-clock to picochess.ini"
echo "... or change picochess.ini file with dgt clock setting dgtpi = True"
echo "NOTE: dgtpi = True setting should be used with care, only for DGTPi clocks"
echo "In case of problems have a look in the log /opt/picochess/logs/picochess.log"
