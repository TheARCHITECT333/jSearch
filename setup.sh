#!/usr/bin/env bash
# Spin up jsearch in Docker for local testing.
#
#   ./setup.sh          build + start, wait until healthy, print URLs
#   ./setup.sh logs     follow logs
#   ./setup.sh down     stop (keeps the SQLite volume)
#   ./setup.sh reset    stop and wipe the SQLite volume
set -euo pipefail
cd "$(dirname "$0")"

command -v docker >/dev/null || { echo "docker not found - install Docker first." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "docker compose v2 not found." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker daemon not running - start Docker Desktop / dockerd." >&2; exit 1; }

case "${1:-up}" in
  logs)  exec docker compose logs -f ;;
  down)  exec docker compose down ;;
  reset) exec docker compose down -v ;;
  up)    ;;
  *)     echo "usage: $0 [up|logs|down|reset]" >&2; exit 2 ;;
esac

docker compose up --build -d

printf "Waiting for backend"
for _ in $(seq 1 90); do
  if curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; then
    printf " ok\n"
    break
  fi
  printf "."; sleep 2
done
curl -fsS http://localhost:8000/api/health >/dev/null 2>&1 || {
  printf "\nBackend not healthy after 3 min. Last logs:\n" >&2
  docker compose logs --tail 40 backend >&2
  exit 1
}

for _ in $(seq 1 30); do
  curl -fsS http://localhost:3000 >/dev/null 2>&1 && break
  sleep 1
done

cat <<EOF

  App      http://localhost:3000
  API      http://localhost:8000/api/health

  LLM on this machine? In the UI use http://host.docker.internal:11434 as the Ollama URL.
  Logs: ./setup.sh logs    Stop: ./setup.sh down
EOF
