# ha_wrapped add-on Dockerfile.
#
# BUILD_FROM is injected per-arch by the HA Supervisor build system (see build.yaml).
# For local testing pass it directly:
#   docker build --build-arg BUILD_FROM=python:3.12-alpine .
ARG BUILD_FROM
FROM $BUILD_FROM

# Install ha-wrapped from GitHub via pip.
# pyproject.toml data-files puts template.html at
# $(python -c "import sys;print(sys.prefix)")/share/ha-wrapped/
# so find_template() picks it up automatically — no file duplication needed.
# Pin to the current release tag; bump this together with config.yaml version.
RUN apk add --no-cache git && \
    pip3 install --no-cache-dir \
      "ha-wrapped @ git+https://github.com/3DJupp/ha-wrapped.git@v1.1.0" && \
    apk del git

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
