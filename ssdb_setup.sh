#!/bin/sh
wget --no-check-certificate https://github.com/ideawu/ssdb/archive/master.zip
unzip master
mv ssdb-master ssdb
cd ssdb
make
