#!/bin/sh
#
# run as normal user
# install a rfcomm on a Debian to communicate with DgtPi
# you need to replace the DEVICE_MAC address value with your DGT board
#
# still experimental, pair, trust, and connect are not done
# as they dont seem to be needed... Its enough to create the rfcomm123
# with connect?
# do we even need to run the bluetoothctl scan here?
#
DEVICE_MAC="00:06:66:FF:6D:EE"

echo "starting bluetooth and asking for agent..."
bluetoothctl <<EOF
agent on
default-agent
EOF

echo "----- wait for agent to be registered..."
sleep 3
echo "----- check above that agent was registered!"

echo "starting scanning"
bluetoothctl <<EOF
scan on
EOF

echo "---------- waiting for scan results - cannot be seen on screen - just wait!"
sleep 5

#echo "trying pair"
#bluetoothctl <<EOF
#pair $DEVICE_MAC
#EOF
#echo "---- waiting for pair results"
#sleep 5

#bluetoothctl <<EOF
#trust $DEVICE_MAC
#EOF
#sleep 1
#bluetoothctl <<EOF
#connect $DEVICE_MAC
#EOF
#sleep 1
bluetoothctl <<EOF
scan off
EOF

echo "creating an rfccomm123 like the one on Raspberry PI"
sudo rfcomm bind /dev/rfcomm123 $DEVICE_MAC 1
echo "waiting for bind to complete so that we can set read/write..."
sleep 2

echo "... Now giving read/write access"
sudo chmod a+rw /dev/rfcomm123
echo "------ Done ------"
ls -la /dev/rfcomm123
echo "check that ls command above has rw for all"
