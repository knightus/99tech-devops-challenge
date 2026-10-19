#!/usr/bin/env bash
# Replays every failure scenario from SOLUTION.md against the running stack
# and prints PASS/FAIL for each. Start the stack first:
#   docker compose up -d --build
# Usage: ./verify.sh            (stack on http://localhost:8080)
#        NGINX_PORT=18080 ./verify.sh
set -u
cd "$(dirname "$0")"

BASE="http://localhost:${NGINX_PORT:-8080}"
pass=0
fail=0

cid() { docker compose ps -aq "$1"; }
code() { curl -s -o /dev/null -m "${2:-10}" -w '%{http_code}' "$BASE$1"; }
secs() { curl -s -o /dev/null -m "${2:-20}" -w '%{time_total}' "$BASE$1"; }

check() {
  local name=$1 ok=$2
  if [ "$ok" = 1 ]; then echo "PASS  $name"; pass=$((pass + 1));
  else echo "FAIL  $name"; fail=$((fail + 1)); fi
}

# Wait up to $2 seconds for $1 to return 200.
wait_200() {
  local t=0
  until [ "$(code "$1" 3)" = 200 ]; do
    sleep 1; t=$((t + 1)); [ $t -ge "${2:-30}" ] && return 1
  done
  return 0 # the loop's own status is its last body command, not success
}

burst() { for _ in $(seq 1 10); do curl -s -o /dev/null -m 20 "$BASE/api/users" & done; wait; }

echo "Target: $BASE"
wait_200 /status 60 || { echo "Stack not reachable at $BASE"; exit 1; }

# 1. nginx routes /api to the port the API listens on.
check "GET /api/users returns 200" "$([ "$(code /api/users)" = 200 ] && echo 1)"

# 2. Welcome page renders instead of downloading.
ctype=$(curl -s -o /dev/null -w '%{content_type}' "$BASE/")
check "GET / is text/plain" "$([[ $ctype == text/plain* ]] && echo 1)"

# 3. Health endpoints reachable through nginx.
check "GET /status returns 200" "$([ "$(code /status)" = 200 ] && echo 1)"
check "GET /ready returns 200" "$([ "$(code /ready)" = 200 ] && echo 1)"

# 4. Postgres restart: API fails fast, stays alive, recovers on its own.
api_before=$(docker inspect -f '{{.State.StartedAt}}' "$(cid api)")
docker stop "$(cid postgres)" >/dev/null
check "Postgres down: /api/users answers 500 (no hang)" "$([ "$(code /api/users 8)" = 500 ] && echo 1)"
check "Postgres down: /ready is 503, /status still 200" \
  "$([ "$(code /ready 8)" = 503 ] && [ "$(code /status)" = 200 ] && echo 1)"
docker start "$(cid postgres)" >/dev/null
check "Postgres back: /api/users recovers" "$(wait_200 /api/users 60 && echo 1)"
api_after=$(docker inspect -f '{{.State.StartedAt}}' "$(cid api)")
check "API process survived the Postgres restart" "$([ "$api_before" = "$api_after" ] && echo 1)"

# 5. Frozen Postgres: requests time out instead of hanging.
docker pause "$(cid postgres)" >/dev/null
t=$(secs /api/users)
check "Postgres frozen: request fails within 7s (took ${t}s)" "$(awk -v t="$t" 'BEGIN{print (t<7)?1:0}')"
docker unpause "$(cid postgres)" >/dev/null
wait_200 /api/users 30

# 6. Pool leak: repeated query failures must not exhaust the pool.
leak_ok=1
for round in 1 2 3 4 5 6; do
  burst
  docker pause "$(cid postgres)" >/dev/null
  burst
  docker unpause "$(cid postgres)" >/dev/null
  wait_200 /api/users 15 || { leak_ok=0; echo "      pool exhausted after round $round"; break; }
done
check "6 rounds of failed queries leave the pool usable" "$leak_ok"

# 7. Redis outage does not fail the request.
docker stop "$(cid redis)" >/dev/null
check "Redis down: /api/users still 200" "$([ "$(code /api/users)" = 200 ] && echo 1)"
check "Redis down: /ready is 503" "$([ "$(code /ready)" = 503 ] && echo 1)"
docker start "$(cid redis)" >/dev/null
wait_200 /ready 30

# 8. Crashed API process is restarted automatically.
docker exec "$(cid api)" sh -c 'kill -9 "$(pidof node)"'
check "API crash: restarted and serving again" "$(wait_200 /api/users 60 && echo 1)"

# 9. Recreated API gets a new IP; nginx must follow it without a reload.
#    A placeholder container holds the old IP so Docker cannot reuse it.
net=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' "$(cid api)")
docker compose rm -sf api >/dev/null 2>&1
docker run -d --rm --name verify-ip-holder --network "$net" alpine sleep 120 >/dev/null
docker compose up -d api >/dev/null 2>&1
check "API recreated on a new IP: nginx follows it without reload" "$(wait_200 /api/users 60 && echo 1)"
docker rm -f verify-ip-holder >/dev/null

echo "----"
echo "$pass passed, $fail failed"
[ "$fail" = 0 ]
