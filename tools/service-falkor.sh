#!/bin/bash

# This script starts the read-only Datalad-Registry service on the `falkor`
# server. It is meant to be invoked by the `service-falkor.service` `systemd`
# user unit, which retries it on failure. See `tools/service-falkor.service`.

set -eu
umask 077

# Log everything (very important for debugging unattended runs)
exec >> "$HOME/service-falkor.debug.log" 2>&1
echo "=== $(date) starting service-falkor.sh ==="

# `systemd` gives a user unit a minimal `PATH` and does not load any shell
# configuration, so the search path is pinned here. `podman-compose` is
# installed with `pipx`, which places it in `$HOME/.local/bin`.
export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

# `XDG_RUNTIME_DIR` locates Podman's rootless runtime state, and
# `DBUS_SESSION_BUS_ADDRESS` locates the D-Bus session bus over which Podman
# reaches the user's `systemd` manager. Without them Podman cannot create the
# `systemd` cgroups it uses by default and falls back to `cgroupfs`. A user
# unit provides the first, but not always the second.
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
    XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    # A D-Bus address names a transport followed by its parameters, so this is
    # the `unix` transport with its socket at `$XDG_RUNTIME_DIR/bus`.
    DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
fi
export XDG_RUNTIME_DIR DBUS_SESSION_BUS_ADDRESS

# Go to project root
cd "$(dirname "$0")" && cd ..

echo "Working directory: $(pwd)"

# Load environment variables
set -a
# shellcheck disable=SC1091
source "./.env.read-only.falkor"
set +a

echo "Environment loaded"

# Start the service. `--wait`, which requires podman-compose 1.6.0 or later,
# makes the command exit non-zero when a container fails to start, and
# otherwise wait until `read-only-db` is healthy and `read-only-web` is
# running. Too short a timeout is harmless: the unit simply runs this script
# again.
podman-compose -f docker-compose.read-only.yml up -d --wait --wait-timeout 180

echo "=== $(date) finished ==="
