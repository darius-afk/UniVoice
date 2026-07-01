#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

WSL_HOST_IP="$(hostname -I | awk '{print $1}')"
export WSL_HOST_IP

echo "WSL_HOST_IP=$WSL_HOST_IP"

# Ensure Swarm is initialized
if [ "$(docker info -f '{{.Swarm.LocalNodeState}}')" != "active" ]; then
  docker swarm init
fi

# Build local app image
docker build -t univoice-poll-manager:latest poll_manager

# Update Keycloak client redirect URIs to include the current WSL IP
KEYCLOAK_REDIRECT_URIS="http://${WSL_HOST_IP}:5000/*,http://127.0.0.1:5000/*,http://localhost:5000/*" \
  python3 setup_keycloak.py

# Deploy/update stack (uses WSL_HOST_IP for KEYCLOAK_EXTERNAL_URL)
docker stack deploy -c stack.yml univoice_stack

echo "Done. Open: http://${WSL_HOST_IP}:5000"
