FROM eclipse-temurin:25-jre-alpine

ARG UID=1000
ARG GID=1000

# Install packages while we're still root.
WORKDIR /opt/minecraft
RUN --mount=target=/build,source=build /build/install-packages.sh

RUN addgroup -S -g "${GID}" minecraft \
    && adduser -S -D -H -u "${UID}" -G minecraft minecraft \
    && mkdir -p /data /backups /opt/minecraft/versions \
    && chown -R minecraft:minecraft /data /backups /opt/minecraft

COPY --chmod=755 /scripts/ ./scripts/

WORKDIR /data

USER minecraft:minecraft

STOPSIGNAL SIGTERM
ENTRYPOINT ["python", "-u", "/opt/minecraft/scripts/launcher.py"]
