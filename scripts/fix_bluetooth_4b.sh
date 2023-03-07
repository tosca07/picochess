#!/bin/bash 
###########################################################
# Script Name:fix_bluetooth_4b.sh
# Author: Eric Singer (updated by Randy Reade 05/02/2022)
# Date: 04/27/2020
# Description: This script will fix problems with bluetooth
#              connectivity when picochess is running on a
#              Raspberry Pi 4B.
#----------------------------------------------------------

##############################################################
### Wait a few seconds after sysbem boot before continuing ###
##############################################################
sleep 10

###############################################################
### Check to see if bluetooth is running, if not restart it ###
###############################################################

systemctl -q status bluetooth 1>/dev/null 2>&1
if [[ $? -eq 0 ]]
then
   echo "Bluetooth Service is running..."
else
   echo "Bluetooth Service is not running, Restarting..."
   systemctl -q restart bluetooth
   sleep 2
fi

#############################################################
### Check to see if hciuart is running, if not restart it ###
#############################################################
systemctl -q status hciuart 1>/dev/null 2>&1
if [[ $? -eq 0 ]]
then
   echo "hciuart Service is running..."
else
   echo "hciuart Service is not running or failed, Restarting..."
   systemctl -q restart hciuart
   sleep 2
fi

#############################################################
### Loop through all the devices that have been paired to ###
### the Raspberry Pi.  If they are DGT_BT_ or PCS-REVII   ###
### then check if they are connected, if not remove them  ###
#############################################################
/bin/echo -e  'paired-devices  \nquit' |  bluetoothctl|grep -E 'DGT_BT_|PCS-REVII'|cut -d' ' -f2| while read PAIRED
do
   echo "${PAIRED} is paired"
   CONNECTED=` /bin/echo -e  "info ${PAIRED} \nquit" |  bluetoothctl|grep Connected`
   echo ${CONNECTED}|grep no
   if [[ $? -eq 0 ]]
   then 
      /bin/echo -e  "remove ${PAIRED} \nquit"|  bluetoothctl
   fi
done

exit 0
