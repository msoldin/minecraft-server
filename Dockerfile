FROM eclipse-temurin:25-jre-alpine

WORKDIR /opt/minecraft
RUN --mount=target=/build,source=build /build/install-packages.sh
COPY --chmod=755 /scripts/start.sh ./scripts/start.sh
COPY /scripts/ ./scripts/
RUN chmod -R 0755 ./scripts

WORKDIR /data

ENV UID=1000
ENV GID=1000

ENTRYPOINT ["/opt/minecraft/scripts/start.sh"]
