#!/bin/sh
# GearCargo image entrypoint.
#
# Normal run: hand off to the s6-overlay init (PID 1) unchanged.
# `install` : print a self-extracting installer to stdout instead of starting
#             the app, so a host with only Docker (and no repo access) can set up:
#               docker run --rm ghcr.io/aiulian25/gearcargo:latest install > gearcargo-install.sh
#               sh gearcargo-install.sh && ./setup.sh
if [ "${1:-}" = "install" ]; then
    exec sh /install/print-installer.sh
fi
exec /init "$@"
