#!/bin/bash

wget https://archive.org/compress/Syzygy345 -O $(dirname $(realpath "$0"))/Syzygy345.zip
unzip Syzygy345.zip -d syzygy
rm Syzygy345.zip
