FROM eclipse-temurin:25-jre-alpine

WORKDIR /opt/minecraft
RUN --mount=target=/build,source=build /build/install-packages.sh
COPY --chmod=755 /scripts/start.sh ./scripts/start.sh
COPY --chmod=755 /scripts/install-server.py ./scripts/install-server.py

WORKDIR /data

ENV MEMORY_SIZE=1G
ENV UID=1000
ENV GID=1000

ENTRYPOINT ["/opt/minecraft/scripts/start.sh"]
