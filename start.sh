#!/usr/bin/env bash

set -eu -o pipefail

# Enable I2C
modprobe i2c-dev

sudo i2cdetect -y 1

python -u src/main.py
