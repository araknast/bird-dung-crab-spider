#!/bin/sh
while true
do
    ./ssdb/ssdb-server ./ssdb/ssdb.conf -s restart &
    sleep 15 && touch ./DB_IS_OK
    ssdb_pid=$!
    echo "started ssdb server"
    echo "watching db ok file"
    inotifywait -e delete_self ./DB_IS_OK
    echo "db not ok!!!"
    echo "stopping server..."
    kill -2 $ssdb_pid
    sleep 2
    echo "repairing..."
    ./ssdb/tools/ssdb-repair ./ssdb/var/data 
done
