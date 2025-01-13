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

echo "giving communication rights so that hardwired clock can be used"
setcap 'cap_net_bind_service,cap_sys_rawio,cap_dac_override+eip' /usr/bin/python3.11

echo "DGTPi clock installation complete. Please reboot"
echo "You need to copy picochess.ini-example-dgtpi3-clock to picochess.ini"
echo "... or write your own ini file with setting dgtpi = True"
echo "NOTE: dgtpi = True setting should be used with care, only for DGTPi clocks"
echo "In case of problems have a look in the log /opt/picochess/logs/picochess.log"
