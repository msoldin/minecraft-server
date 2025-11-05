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
    chown -vR $USER_ID:$GROUP_ID /data

fi

exec su-exec ${DOCKER_USER}:${DOCKER_GROUP} java -jar -Xms${MEMORY_SIZE} -Xmx${MEMORY_SIZE} -Dlog4j2.formatMsgNoLookups=true -XX:+UseZGC -XX:+AlwaysPreTouch -XX:+UseStringDeduplication -XX:+UseCompactObjectHeaders -jar /opt/minecraft/server.jar nogui