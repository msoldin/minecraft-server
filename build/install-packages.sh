#!/bin/sh

set -e
set -o pipefail

apk add --no-cache -U \
    curl \
    su-exec