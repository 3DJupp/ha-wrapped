ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV LANG=C.UTF-8 PYTHONUNBUFFERED=1

# Which git ref of the engine to install (set in build.yaml / via --build-arg).
ARG HA_WRAPPED_REF=main

# Install the shared engine (wrapped.py + template.html, pulled in as the
# `ha-wrapped` package so its template lands in /usr/share/ha-wrapped/) plus
# aiohttp for the Ingress server. Build deps are dropped again afterwards to
# keep the image small.
RUN apk add --no-cache --virtual .build \
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
