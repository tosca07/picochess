#!/bin/sh
#
# install a rfcomm on a Debian to communicate with DgtPi
# 
# you need to run this script using sudo
# and of course you need to replace the MAC address with your DGT board
# 
# before running this script you need to do the following
# >bluetoothctl
# >scan on
# ... look for the MAC address of your DGT and use it:
# >connect 00:06:66:FF:6D:EE
# >trust 00:06:66:FF:6D:EE
rfcomm bind /dev/rfcomm123 00:06:66:FF:6D:EE 1
chmod a+rw /dev/rfcomm123

