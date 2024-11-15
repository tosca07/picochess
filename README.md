PicoChess
=========

Stand alone chess computer based on Raspberry PI. Supports DGT electronic clocks and many electronic chess boards.
This is an update to fix the technical debt; the existing Picochess was using very old chess and web modules.
This first baseline has the latest chess and web python modules now. The target is to update all python modules.
This version will run on PI Bookworm with the latest python

Requirements
------------

- Raspberry Pi 3 or newer recommended
- RaspiOS Bookworm (latest) recommended

Installation
------------

Run this command as root on your Raspberry Pi:

```
curl -sSL https://raw.githubusercontent.com/ghislainbourgeois/picochess/master/install-picochess.sh | bash
```

If you wish to use engines supported by the Mame emulator, you will also need
to set the GPU Memory Split to 64 Mb minimum.

Once the installation is complete, you can copy the file
`/opt/picochess/picochess.ini.example` to `/opt/picochess/picochess.ini` and
edit it for your specific situation.

**Note**

This repository does not contain all engines, books or voice samples the
community has built over the years. Unfortunately, a lot of those files cannot
be easily hosted in this repository. You can find additional content for your
picochess installation in the [Picochess Google Group](https://groups.google.com/g/picochess).
