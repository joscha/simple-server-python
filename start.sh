#!/usr/bin/env bash

set -eu -o pipefail

# Enable I2C
modprobe i2c-dev

if [[ "${I2CDETECT:-}" == true ]]; then
    sudo i2cdetect -y 1
fi

python -u src/main.py
