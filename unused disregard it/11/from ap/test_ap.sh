#!/bin/bash

while true; do
    echo -n "$(date '+%H:%M:%S') "
    if networksetup -listpreferredwirelessnetworks en0 | grep -q DDDEV; then
        echo "✅ DDDEV network found!"
    else
        echo "❌ DDDEV network not found"
    fi
    sleep 2
done