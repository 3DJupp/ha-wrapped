#!/usr/bin/with-contenv bashio
# shellcheck shell=bash
bashio::log.info "Starting HA Wrapped Ingress server ..."
exec python3 /app/server.py
