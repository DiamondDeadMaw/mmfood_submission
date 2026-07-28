#!/bin/bash
set -e
python3 server/main.py &
nginx -g 'daemon off;'

