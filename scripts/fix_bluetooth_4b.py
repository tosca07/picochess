###########################################################
# Script Name:fix_bluetooth_4b.py
# Author: Eric Singer (updated by Randy Reade 05/02/2022)
# Date: 05/10/2020
# Description: This script will fix problems with bluetooth
#              connectivity when picochess is running on a
#              Raspberry Pi 4B.
###########################################################
import os
import subprocess
import time

##########################################################
# Wait a few seconds after sysbem boot before continuing #
##########################################################
time.sleep(8)

###########################################################
# Check to see if bluetooth is running, if not restart it #
###########################################################
status = os.system("systemctl is-active --quiet bluetooth")
if status != 0:
    print("Bluetooth Service is not running, Restarting...")
    os.system("systemctl restart bluetooth")
else:
    print("Bluetooth Service is running...")

#########################################################
# Check to see if hciuart is running, if not restart it #
#########################################################
status = os.system("systemctl is-active --quiet systemctl status hciuart")
if status != 0:
    print("hciuart Service is not running or failed, Restarting...")
    os.system("systemctl restart hciuart")
else:
    print("hciuart Service is running...")

#########################################################
# Loop through all the devices that have been paired to #
# the Raspberry Pi.  If they are DGT_BT_ or PCS-REVII   #
# then check if they are connected, if not remove them  #
#########################################################
paired_devices_cmd = "/bin/echo -e  'paired-devices  \nquit' |  bluetoothctl|grep -E 'DGT_BT_|PCS-REVII'|cut -d' ' -f2"
paired = subprocess.run(paired_devices_cmd, shell=True, check=True, stdout=subprocess.PIPE, universal_newlines=True)
for bt_device in paired.stdout.splitlines():
    print("Found ", bt_device)
    info_cmd = "/bin/echo -e  'info " + bt_device + " \nquit' |  bluetoothctl|grep Connected"
    connected = subprocess.run(info_cmd, shell=True, check=True, stdout=subprocess.PIPE, universal_newlines=True)
    if connected.stdout.find("Connected: no") > 0:
        print("Device ", bt_device, " is not connected.  Removing...")
        remove_cmd = '/bin/echo -e  "remove ' + bt_device + ' \nquit"|  bluetoothctl'
        subprocess.run(remove_cmd, shell=True, stdout=subprocess.PIPE)

quit()
