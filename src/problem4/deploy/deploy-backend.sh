#!/usr/bin/env bash
# Runs ON the EC2 instance, invoked by the pipeline through SSM Run Command:
#   /opt/api/deploy-backend.sh <account>.dkr.ecr.<region>.amazonaws.com/api:<git-sha>
#
# Swaps the running API container for the given image, health-checks it, and
# reverts to the previous image if the new one is unhealthy. The instance
# profile grants ECR pull; configuration lives in /etc/api/env (provisioned
# from Secrets Manager at launch), never in the image.
set -euo pipefail

IMAGE="${1:?usage: deploy-backend.sh <image>}"
NAME=api
ENV_FILE=/etc/api/env
HEALTH_URL=http://localhost:3000/status
STATE=/opt/api/current-image   # last known-good image, used for rollback

log() { echo "[deploy] $*"; }

[ -f "$ENV_FILE" ] || { log "ERROR: $ENV_FILE missing"; exit 1; }

registry="${IMAGE%%/*}"
region=$(echo "$registry" | cut -d. -f4)
aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "$registry" >/dev/null

log "pulling $IMAGE"
docker pull --quiet "$IMAGE"

previous=""
[ -f "$STATE" ] && previous=$(cat "$STATE")

start() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" --restart unless-stopped --init \
    --env-file "$ENV_FILE" -p 3000:3000 "$1" >/dev/null
}

healthy() {
  for i in $(seq 1 15); do
    if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null; then return 0; fi
    log "health check $i/15 failed"
    sleep 2
  done
  return 1
}

start "$IMAGE"
if healthy; then
  echo "$IMAGE" > "$STATE"
  log "live: $IMAGE"
  docker image prune -af --filter "until=168h" >/dev/null || true
  exit 0
fi

log "UNHEALTHY: $IMAGE"
docker logs --tail 50 "$NAME" || true
if [ -n "$previous" ]; then
  log "reverting to $previous"
  start "$previous"
  healthy && log "reverted; previous image is serving" || log "CRITICAL: previous image also unhealthy"
else
  log "no previous image to revert to (first deploy)"
fi
exit 1
