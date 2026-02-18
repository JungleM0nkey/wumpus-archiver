#!/bin/sh
# Ensure /data is writable by the archiver user (UID 1000).
# Bind mounts may be owned by root; fix ownership if running as root.
if [ "$(id -u)" = "0" ]; then
    chown -R archiver:archiver /data 2>/dev/null || true
    exec gosu archiver tini -- "$@"
fi
exec tini -- "$@"
