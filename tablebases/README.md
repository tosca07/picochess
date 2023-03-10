General
=======
This folder is for tablebases files. They are not provided with picochess
because of their size. However, a script is provided to download the Syzygy
tablebases for 3, 4 and 5 pieces endgames from the Internet Archive.

To use this script, you will need to install `wget` and `unzip`. You can do so
with:

`apt install wget unzip`

You can then run the script from this folder:

`./download-syzygy345.sh`

Please note that this will take several minutes to download, depending on your
Internet connection. It will also require 2Gb of free space to run, and 1Gb
once completed.
