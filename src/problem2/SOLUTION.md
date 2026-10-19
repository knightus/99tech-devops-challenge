# Problem 2: NGINX VM at 99% disk

A VM that only runs NGINX shouldn't fill 64 GB. Something is being written and never cleaned up, most likely logs. Find out what before deleting anything.

## Contents

- [Troubleshooting](#troubleshooting)
- [Likely causes](#likely-causes)
- [Impact](#impact)
- [Prevention](#prevention)

## Troubleshooting

1. `df -h` and `df -i`: have bytes or inodes run out?
2. `du -xh / --max-depth=2 | sort -h`: where is the space? Usually `/var/log`.
3. If `df` says full but `du` doesn't add up: `lsof +L1` lists files that were deleted but are still open.
4. Check `/var/log/nginx`, `journalctl --disk-usage`, and `/etc/logrotate.d/nginx`.

## Likely causes

| Cause | Sign | Recover | Prevent |
|---|---|---|---|
| Access logs not rotated | Huge `access.log` | `truncate -s 0` the live log; compress or move old ones | Daily rotation with compression; ship logs off the box |
| Deleted log still open | `df` full, `du` small, `lsof +L1` shows `(deleted)` | `nginx -s reopen` (no restart) | logrotate `postrotate` signals NGINX; never `rm` a live log |
| Proxy cache / temp files | Big `/var/cache/nginx` | Clear the cache | `max_size` on `proxy_cache_path` |
| journald | `journalctl --disk-usage` in GB | `journalctl --vacuum-size=500M` | `SystemMaxUse=` |
| OS leftovers | apt cache, old kernels, core dumps | `apt clean`, `apt autoremove` | Scheduled cleanup |

Reproduced the first two on a 64 MB disk (`reproduce-disk-full.sh`):

```
traffic:          100% full, access.log = 64M
GET /          -> 200, but nothing logged
rm access.log  -> still 100%, du = 0
lsof +L1       -> nginx ... access.log (deleted)
nginx -s reopen-> 0%
```

`reopen` beats a restart: a load balancer restart drops live connections.

## Impact

- NGINX keeps serving but silently stops logging. In my test there was no error at all.
- Uploads too big for NGINX's memory buffer are written to disk first, so they fail.
- apt and SSH can fail, which makes the fix harder.
- It's the load balancer, so every service behind it is hit.

## Prevention

- Alert at 80% disk/inodes, plus "full within 24h". 99% is far too late.
- Ship logs to S3 + Athena (~$0.023/GB/month), not CloudWatch Logs (~$0.50/GB ingested, which can cost more than the VM).
- Don't log health-check requests.
- A bigger disk (~$0.08/GB/month) only delays the next incident.

**Assumptions:** stock Ubuntu NGINX with the default logrotate. I can't see the VM, so the causes are ranked guesses; the `du` step finds anything else.
