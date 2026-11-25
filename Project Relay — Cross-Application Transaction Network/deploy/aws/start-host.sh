#!/usr/bin/env bash
# Run on the prepared EC2 host; safe to repeat, preserving .env and named volumes.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"
umask 077
python3 -m relay.init_env
docker compose -f compose.yaml -f deploy/aws/compose.aws.yaml up --build -d --wait --wait-timeout 180
curl -fsS --retry 5 --retry-connrefused http://127.0.0.1:8090/healthz
printf '\nProject Relay services started. Retrieve the API token from the private .env through your SSH-less SSM session.\n'
