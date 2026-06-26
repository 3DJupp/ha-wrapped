ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 PYTHONUNBUFFERED=1

# Which git ref of the engine to install (set in build.yaml / via --build-arg).
ARG HA_WRAPPED_REF=main
# Cache-bust token, bumped to the add-on version on every release (build.yaml).
# HA_WRAPPED_REF is a moving branch (main), so without this the pip layer below
# would be served from Docker's cache on a version bump and ship a stale
# wrapped.py while config.yaml already advertises the new version. Referencing
# it in the RUN command invalidates that layer whenever the version changes, so
# the engine is always re-pulled in lock-step with the add-on version.
ARG ENGINE_CACHE_BUST=dev

# Install the shared engine (wrapped.py + template.html, pulled in as the
# `ha-wrapped` package so its template lands in /usr/share/ha-wrapped/) plus
# aiohttp for the Ingress server. Build deps are dropped again afterwards to
# keep the image small.
RUN echo "engine ref=${HA_WRAPPED_REF} build=${ENGINE_CACHE_BUST}" \
    && apk add --no-cache --virtual .build \
        git gcc musl-dev python3-dev yaml-dev libffi-dev \
    && pip install --no-cache-dir \
        aiohttp \
        "ha-wrapped @ git+https://github.com/3DJupp/ha-wrapped@${HA_WRAPPED_REF}" \
    && apk del .build

COPY server.py /app/server.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh

WORKDIR /data
CMD [ "/run.sh" ]
