#!/bin/bash
# usage: render.sh <svg> <png> : 1024x1024, 투명 배경
E="/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
prof="$(dirname "$2")/prof_$(basename "$2" .png)"
"$E" --headless=new --disable-gpu --hide-scrollbars --default-background-color=00000000 --force-device-scale-factor=2 --user-data-dir="$prof" --window-size=1024,1024 --screenshot="$2" "file:///$1" >/dev/null 2>&1
for i in $(seq 1 40); do [ -s "$2" ] && break; sleep 0.5; done
