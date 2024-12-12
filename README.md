PicoChess
=========

Stand alone chess computer based on Raspberry PI. Supports DGT electronic clocks and many electronic chess boards. You dont need DGT hardware, you can use a web browser (default installation) You can play Stockfish 17 or LC0. LC0 has a really small neural net, but you can download larger. Debian x86_64 is also supported, at least the webplay works. At the moment Debian only has Stockfish 17, I have not yet compiled LC0 for Debian.

This is a long term update to fix the technical debt of the picochess, the existing Picochess was using very old python chess and web modules. This first baseline has the latest chess and web python modules now. The target is to update all python modules. The program is not yet fully async but the target is to convert most things to async. Maybe all the threads wont be needed any more then.

Requirements
------------

- Raspberry Pi 3, or Pi 4 (aarch64) or Debian (x86_64)
- RaspiOS Bookworm (latest) 64bit recommended

Installation
------------
Note: Everything is really early and experimental and installation script has only been testad with PI 4 64bit. D
I have done some initial basic testing with a browser and a DGT bluetooth board. The install script has not been tested with a DGT board yet. I have only tested PI 4 64bit so far.

1. You need a Raspberry PI 4 (or 3) and a 32G SD card.
2. Use Raspberry Pi Imager to crete a PI operating system on your SD card as follows:
3. Choose PI 4 and 64bit OS (I have not tested PI 3 yet, but feel free to test)
4. Username is assumed to be pi which should be standard on the imager. You can make sure by changing options before writing to the SD card.
5. If you don't not use a network cable on your PI define your WiFi settings.
6. Add ssh support if you don't work locally on the PI with attached screen, keyboard and mouse.
7. Write the image to the SD.
8. Boot your PI with the SD card inserted. A standard image will boot after first start, and the second time it starts you should be able to login as user pi.
9. Using sudo raspi-config make changes to advanced options: select PulseAudio and X11. Without PulseAudio the picochess spoken voice can lag.
10. Get this repo. First cd /opt then do sudo git clone. This should create your /opt/picochess folder.
11. In the picochess folder run the sudo install-picochess.sh script. This install script will do git clone if you dont have the repo, and git pull if you already have it to get updates.
12. install script will update the PI system before starting.
13. Reboot when install is done.
14. Open your web browser on localhost:8080 or from another computer using the IP address of your PI. You can change the web port in pocochess.ini
15. Start playing !

Tailoring: edit the picochess.ini file.
Troubleshooting: check the log in /opt/picochess/logs/picochess.log
Google group for reporting and discussing: https://groups.google.com/g/picochess

**Note**

This repository does not contain all engines, books or voice samples the
community has built over the years. Unfortunately, a lot of those files cannot
be easily hosted in this repository. You can find additional content for your
picochess installation in the [Picochess Google Group](https://groups.google.com/g/picochess).
