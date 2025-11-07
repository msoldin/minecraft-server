#!/bin/sh

set -e
set -o pipefail

apk add --no-cache -U \
    libstdc++ \
    curl \
    su-exec \
    libudev-zero \
    python3 \
    py3-pip

pip install --no-cache-dir --break-system-packages -r /build/requirements.txt