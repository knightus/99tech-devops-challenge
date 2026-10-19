# Problem 3 — Fixing the unreliable API

"Unreliable and sometimes inaccessible" turned out to be several bugs at once. One broke every request. The others only appeared when something went wrong: a database restart, a slow database, or a redeploy.

To check the fixes:

```bash
cd src/problem3
cp .env.example .env
docker compose up -d --build
./verify.sh        # breaks things on purpose and checks the stack recovers: 14/14 pass
```

## What was wrong

| # | Problem | Effect | Fix |
|---|---|---|---|
| 1 | nginx sent traffic to port 3001; the API listens on 3000 | Every `/api` request returned 502 | Correct the port |
| 2 | No handler for the Postgres pool's `error` event | A database restart crashed the API, and it stayed down | Add `pool.on('error')`, plus `restart: unless-stopped` |
| 3 | No timeouts anywhere (pg, Redis, nginx) | A slow database made requests hang until nothing could be served | Timeouts of 3–5s in the app and 10s in nginx |
| 4 | `release()` skipped when a query failed | Each failure leaked a pool slot until the API was dead | Use `pool.query()` |
| 5 | nginx looked up the `api` hostname only once, at startup | After a redeploy, nginx kept sending traffic to the old container's IP and returned 502 | `resolver` + hostname in a variable |
| 6 | `depends_on` didn't wait for Postgres to be ready | Requests failed right after startup | Healthchecks + `service_healthy` |
| 7 | A Redis write failure failed the whole request | Redis down meant 500, even though the data was read fine | Make that write best-effort |

Smaller fixes: `/` was served as a file download, the health endpoints weren't reachable through nginx (I added `/status` and `/ready`), credentials were hardcoded (moved to `.env`), there was no lockfile, the container ran as root, Postgres had no named volume, and an obsolete `version:` key was present. I deleted `init.sql`: it was never mounted, and if it had been, its limit of 20 connections would fill up with only two API replicas.

## How I found them

I worked through each hop: browser → nginx → API → database.

The nginx log said `upstream: ...:3001` and the API log said `running on 3000`. Calling the API directly from inside its container (`docker compose exec api wget -qO- localhost:3000/api/users`) worked. That one command showed the API and the database were fine, so the problem was between nginx and the API.

For the rest, I broke things on purpose and watched what happened:

- **Stopped Postgres.** The API process died with `Unhandled 'error' event` (#2).
- **Froze Postgres** with `docker pause`. Requests hung with no end (#3).
- **Froze Postgres repeatedly** once timeouts were in place. After a few rounds every request failed even though Postgres was healthy, and `pg_stat_activity` showed all 10 pool connections stuck (#4). The leak was hidden until I fixed #3: without timeouts, a stalled query just hangs and never errors.
- **Recreated the API container** so it got a new IP. nginx kept trying the old IP (#5). I only found this one with `verify.sh`, after everything else was fixed.

Each fix is its own commit, so `git log` shows them in the order I found them.

## Monitoring I'd add

- **nginx 5xx rate** above 1%: would have caught #1, #2 and #5 within minutes.
- **p99 latency** above 1s: catches #3 while it builds up.
- **Pool clients waiting** above 0: the only signal for #4. CPU, memory and container status all looked normal while it happened.
- **`/ready` failing** and **container restart count**: dependency loss and crash loops.

## Preventing it in production

- Run `verify.sh` in CI. Every bug here shows up when you test failures, not when everything is working.
- Every network call needs a timeout. Treat a missing timeout as a review blocker.
- Restart policies, healthchecks and `init: true` should come from a service template, not be decided per service.
- Reach services by DNS or service discovery, never by a fixed IP. Keep secrets out of the code.

**Cost:** none of this adds infrastructure. It replaces someone restarting containers by hand after every database blip and every deploy.

**Not done:** graceful shutdown (finishing in-flight requests before exit), and exporting app metrics such as the pool counters.
