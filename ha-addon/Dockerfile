# HA Wrapped add-on Dockerfile.
#
# BUILD_FROM is injected by the HA Supervisor build system; it resolves to
# the architecture-specific Python base image, e.g.:
#   ghcr.io/home-assistant/aarch64-base-python:3.12-alpine3.20
#
# When building locally for testing you can pass it directly:
#   docker build --build-arg BUILD_FROM=python:3.12-alpine .
ARG BUILD_FROM
FROM $BUILD_FROM

WORKDIR /app

# Install Python dependencies first so they are cached separately
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the application files
# In a real add-on repo these live at the repository root
COPY wrapped.py template.html ./

# Add-on entrypoint
COPY ha-addon/run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
