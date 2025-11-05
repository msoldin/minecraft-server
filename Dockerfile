FROM eclipse-temurin:25-jre-alpine

ARG MINECRAFT_VERSION=1.21.10
ARG FABRIC_LOADER_VERSION=0.17.3
ARG FABRIC_INSTALLER_VERSION=1.1.0

WORKDIR /opt/minecraft
RUN --mount=target=/build,source=build /build/install-packages.sh
RUN --mount=target=/build,source=build /build/install-fabric.sh $MINECRAFT_VERSION $FABRIC_LOADER_VERSION $FABRIC_INSTALLER_VERSION
COPY --chmod=755 /scripts/start.sh ./scripts/start.sh

WORKDIR /data

ENV MEMORY_SIZE=1G
ENV UID=1000
ENV GID=1000

ENTRYPOINT ["/opt/minecraft/scripts/start.sh"]
