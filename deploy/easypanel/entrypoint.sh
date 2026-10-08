#!/bin/sh
set -eu
umask 077
if [ "$(id -u)" = 0 ]; then
    mkdir -p /data /models
    chown 10001:10001 /data /models
    exec gosu locutor "$0" "$@"
fi
# CLI commands (users/tests/benchmark) must not download or load a second web model.
if [ "${1:-}" = uvicorn ]; then
    python -m scripts.container_prepare
fi
exec "$@"
