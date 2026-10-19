const express = require("express");
const { Pool } = require("pg");
const Redis = require("ioredis");

const app = express();

const pool = new Pool({
  host: process.env.DB_HOST,
  user: "postgres",
  password: "postgres",
  database: "postgres",
  port: 5432,
});

// Postgres can drop idle pooled connections (restart, failover, network blip).
// pg reports that as an 'error' event on the pool; with no listener Node treats
// it as an uncaught exception and the whole API process exits.
pool.on("error", (err) => {
  console.error("[pg] idle client error:", err.message);
});

const redis = new Redis({ host: process.env.REDIS_HOST, port: 6379 });

// Same rule for ioredis: an unlistened 'error' event must never be able to
// take the process down.
redis.on("error", (err) => {
  console.error("[redis] error:", err.message);
});

app.get("/api/users", async (req, res) => {
  try {
    const db = await pool.connect();
    const result = await db.query("SELECT NOW()");
    db.release();

    await redis.set("last_call", Date.now());
    res.json({ ok: true, time: result.rows[0] });
  } catch (err) {
    console.error(err);
    res.status(500).json({ ok: false, error: err.message });
  }
});

app.get("/status", (req, res) => {
  res.json({ status: "ok" });
});

app.listen(3000, () => console.log("API running on 3000"));
