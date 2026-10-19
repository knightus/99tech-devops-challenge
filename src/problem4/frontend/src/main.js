// Minimal SPA used to exercise the frontend pipeline: it reports API health.
const el = document.getElementById("status");

fetch("/status")
  .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
  .then((body) => (el.textContent = body.status))
  .catch(() => (el.textContent = "unreachable"));
