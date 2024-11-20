FROM eclipse-temurin:21-jre-alpine

ARG MINECRAFT_VERSION=1.19.4
ARG FABRIC_LOADER_VERSION=0.14.19
ARG FABRIC_INSTALLER_VERSION=0.11.2

WORKDIR /opt/minecraft
RUN --mount=target=/build,source=build /build/install-packages.sh
RUN --mount=target=/build,source=build /build/install-fabric.sh $MINECRAFT_VERSION $FABRIC_LOADER_VERSION $FABRIC_INSTALLER_VERSION
COPY --chmod=755 /scripts/start.sh ./scripts/start.sh

WORKDIR /data

ENV MEMORY_SIZE=1G
ENV UID=1000
ENV GID=1000

ENTRYPOINT ["/opt/minecraft/scripts/start.sh"]
