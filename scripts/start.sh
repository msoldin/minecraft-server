#!/bin/sh

set -e

DOCKER_USER='minecraft'
DOCKER_GROUP='minecraft'

# On first startup
if ! id "$DOCKER_USER" >/dev/null 2>&1; then
    
    USER_ID=${UID:-9001}
    GROUP_ID=${GID:-9001}
    echo "Starting with $USER_ID:$GROUP_ID (UID:GID)"

    addgroup --gid $GROUP_ID $DOCKER_GROUP
    adduser $DOCKER_USER --shell /bin/sh --uid $USER_ID --ingroup $DOCKER_GROUP --disabled-password --gecos ""
    mkdir -p /opt/minecraft
    chown -vR $USER_ID:$GROUP_ID /data
    chown -vR $USER_ID:$GROUP_ID /backups
    chown -vR $USER_ID:$GROUP_ID /opt/minecraft
fi

su-exec "${DOCKER_USER}:${DOCKER_GROUP}" python /opt/minecraft/scripts/launcher.py