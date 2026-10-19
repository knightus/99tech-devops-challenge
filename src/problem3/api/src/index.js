const express = require("express");
const { Pool } = require("pg");
const Redis = require("ioredis");

const app = express();

const pool = new Pool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME,
  port: 5432,
  // pg's defaults wait forever. Fail fast instead so a stalled database
  // produces a quick 500 rather than requests piling up indefinitely.
  connectionTimeoutMillis: 3000,
  query_timeout: 5000,
});

// Postgres can drop idle pooled connections (restart, failover, network blip).
// pg reports that as an 'error' event on the pool; with no listener Node treats
// it as an uncaught exception and the whole API process exits.
pool.on("error", (err) => {
  console.error("[pg] idle client error:", err.message);
});

const redis = new Redis({
  host: process.env.REDIS_HOST,
  port: 6379,
  connectTimeout: 2000,
  // By default ioredis queues commands while disconnected, so requests hang
  // during a Redis outage. Error immediately instead.
  enableOfflineQueue: false,
  maxRetriesPerRequest: 1,
});

// Same rule for ioredis: an unlistened 'error' event must never be able to
// take the process down.
redis.on("error", (err) => {
  console.error("[redis] error:", err.message);
});

app.get("/api/users", async (req, res) => {
  try {
    // pool.query returns the client to the pool even when the query throws.
    // The old connect/query/release skipped release() on error, leaking one
    // pool slot per failed query until the pool was exhausted.
    const result = await pool.query("SELECT NOW()");

    // last_call is a best-effort timestamp; a Redis outage must not turn a
    // successful database read into a 500.
    redis
      .set("last_call", Date.now())
      .catch((err) => console.error("[redis] set last_call failed:", err.message));
    res.json({ ok: true, time: result.rows[0] });
  } catch (err) {
    console.error(err);
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Liveness: the process is up. Deliberately checks no dependencies, so a
// database blip never gets a healthy API container restarted.
app.get("/status", (req, res) => {
  res.json({ status: "ok" });
});

// Readiness: this instance can serve real traffic right now. A load balancer
// should stop routing here (not restart it) while this returns 503.
app.get("/ready", async (req, res) => {
  const checks = {};
  await Promise.all([
    pool.query("SELECT 1").then(() => (checks.postgres = "ok"), (e) => (checks.postgres = e.message)),
    redis.ping().then(() => (checks.redis = "ok"), (e) => (checks.redis = e.message)),
  ]);
  const ready = checks.postgres === "ok" && checks.redis === "ok";
  res.status(ready ? 200 : 503).json({ ready, checks });
});

app.listen(3000, () => console.log("API running on 3000"));
