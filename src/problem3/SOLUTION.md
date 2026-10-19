# Problem 3: Stabilizing the Docker Compose Platform

The reported symptom, "unreliable and sometimes inaccessible", was caused by several independent defects. One failed every request; the others appeared only under failure conditions: a database restart, a slow database, or a redeployment.

To verify the fixes:

```bash
cd src/problem3
cp .env.example .env
docker compose up -d --build
./verify.sh        # injects each failure and checks recovery: 14/14 pass
```

## Contents

- [Issues Found](#issues-found)
- [Diagnosis](#diagnosis)
- [Monitoring and Alerts](#monitoring-and-alerts)
- [Prevention](#prevention)

## Issues Found

| # | Issue | Effect | Fix |
|---|---|---|---|
| 1 | nginx proxied to port 3001; the API listens on 3000 | Every `/api` request returned 502 | Correct the upstream port |
| 2 | No listener for the Postgres pool `error` event | A database restart crashed the API permanently | `pool.on('error')` and `restart: unless-stopped` |
| 3 | No timeouts in pg, Redis or nginx | A slow database caused requests to hang until capacity was exhausted | 3-5 s timeouts in the API, 10 s in nginx |
| 4 | `release()` skipped when a query failed | Each failed query leaked a pool connection until the pool was exhausted | `pool.query()` |
| 5 | nginx resolved the `api` hostname only at startup | After redeployment, traffic went to the old container IP (502) | `resolver` with the hostname in a variable |
| 6 | `depends_on` did not wait for readiness | Requests failed immediately after startup | Healthchecks with `condition: service_healthy` |
| 7 | A Redis write failure failed the request | Redis outage returned 500 despite a successful database read | Best-effort Redis write |

Additional fixes:

| Issue | Fix |
|---|---|
| `/` served as `application/octet-stream` | `default_type text/plain` |
| Health endpoints not routed through nginx | `/status` (liveness) and `/ready` (readiness) |
| Hardcoded credentials | `.env` with required-variable checks |
| No lockfile; container ran as root | `package-lock.json`, `npm ci`, `USER node` |
| No named volume for Postgres | `pgdata` volume |
| Obsolete `version:` key; unused `init.sql` and `nginx.conf` | Removed. `init.sql` would have set `max_connections = 20`, exhausted by two API replicas |

## Diagnosis

Each hop was checked in order: client, nginx, API, database.

The nginx log reported `upstream: ...:3001` while the API logged `running on 3000`. A request issued from inside the API container (`docker compose exec api wget -qO- localhost:3000/api/users`) succeeded, confirming the API and database were healthy and isolating the fault to the nginx-to-API hop.

The remaining issues were found by failure injection:

| Test | Observation | Issue |
|---|---|---|
| Stop Postgres | API process exited with `Unhandled 'error' event` | #2 |
| Pause Postgres | Requests hung indefinitely | #3 |
| Repeated pauses, after timeouts were added | All requests failed while Postgres was healthy; `pg_stat_activity` showed all 10 pool connections held | #4 |
| Recreate the API container on a new IP | nginx continued routing to the old IP | #5 |

Issue #4 was masked by #3: without timeouts, a stalled query hangs instead of failing, so the leaking code path was never reached. Issue #5 was found by `verify.sh` after all other fixes were in place. Each fix is a separate commit.

## Monitoring and Alerts

| Signal | Threshold | Detects |
|---|---|---|
| nginx 5xx rate | > 1% for 2 min | #1, #2, #5 |
| p99 latency | > 1 s | #3 |
| Pool clients waiting | > 0 for 1 min | #4 (CPU, memory and container status remained normal during this failure) |
| `/ready` failures, container restarts | 2 consecutive / > 3 in 10 min | Dependency loss, crash loops |

## Prevention

| Practice | Rationale |
|---|---|
| Run `verify.sh` in CI | Every defect here surfaced only under failure conditions |
| Mandatory timeouts on network clients | Enforced in code review |
| Standard service template | Restart policy, healthcheck and `init: true` applied to every service |
| Service discovery instead of fixed IPs | Prevents stale upstream addresses |
| Secrets outside the codebase | Environment variables or a secrets manager |

**Cost:** no additional infrastructure; the changes are configuration and application code.

**Out of scope:** graceful shutdown of in-flight requests, and exporting application metrics such as pool counters.
