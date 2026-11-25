#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
case "${1:-help}" in
  init) exec python3 -m relay.init_env ;;
  up) exec docker compose up -d --build ;;
  down) exec docker compose down ;;
  logs) exec docker compose logs -f ;;
  test) exec python3 -m unittest discover -s tests ;;
  *) echo "Usage: ./run.sh init | up | down | logs | test" ;;
esac
