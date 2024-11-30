PicoChess
=========

Stand alone chess computer based on Raspberry PI. Supports DGT electronic clocks and many electronic chess boards. You dont need DGT hardware, you can use a web browser (default ini file setup) You can play Stockfish 17 or LC0. LC0 has a really small neural net, but you can download larger.

This is a long term update to fix the technical debt of the picochess, the existing Picochess was using very old python chess and web modules. This first baseline has the latest chess and web python modules now. The target is to update all python modules. The program is not yet fully async but the target is to convert everything to async. Maybe all the threads wont be needed any more then.
This version will run on PI Bookworm with python 3.11 or later.

Requirements
------------

- Raspberry Pi 3 or newer recommended
- Development is done on a Pi 4 so Stockfish 17 and LC0 and ini file is for PI 4 aarch64
- RaspiOS Bookworm (latest) recommended

Installation
------------
Note: Everything is really early and experimental and setups have not been verified yet
1. On a standard image make sure you have PulseAudio and X11.
2. Start by downloading install-picochess.sh file and run it (with sudo)
3. Start the picochess program using picochess.sh or manually (sudo not needed)
4. Open your web browser on localhost:8080 or from another computer. You can change the web port in ini.

Tailoring: edit the picochess.ini file.
Troubleshooting: check the log in /opt/picochess/logs/picochess.log
Google group for reporting and discussing: https://groups.google.com/g/picochess

**Note**

This repository does not contain all engines, books or voice samples the
community has built over the years. Unfortunately, a lot of those files cannot
be easily hosted in this repository. You can find additional content for your
picochess installation in the [Picochess Google Group](https://groups.google.com/g/picochess).
