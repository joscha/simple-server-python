#!/usr/bin/env bash

set -eu -o pipefail

# Enable I2C
modprobe i2c-dev

# sudo i2cdetect -y 1

# sudo python -u src/main.py

sudo python -u lcd_i2c.py