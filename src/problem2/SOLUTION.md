# Problem 2: NGINX Load Balancer at 99% Disk Usage

A VM that only runs NGINX should not consume 64 GB. Persistent high usage indicates data that is written continuously and never cleaned up, most commonly logs. The cause must be identified before any data is deleted.

## Contents

- [Troubleshooting](#troubleshooting)
- [Likely Causes](#likely-causes)
- [Impact](#impact)
- [Prevention](#prevention)

## Troubleshooting

Read-only checks, in order:

| Step | Command | Purpose |
|---|---|---|
| 1 | `df -h`, `df -i` | Determine whether blocks or inodes are exhausted |
| 2 | `du -xh / --max-depth=2 \| sort -h` | Locate the largest directories, typically `/var/log` |
| 3 | `lsof +L1` | Find deleted files still held open (when `df` and `du` disagree) |
| 4 | `ls -lh /var/log/nginx`, `journalctl --disk-usage`, `/etc/logrotate.d/nginx` | Confirm log volume and rotation configuration |

## Likely Causes

Ranked by likelihood for a single-purpose NGINX host.

| Cause | Indicator | Recovery | Prevention |
|---|---|---|---|
| Access logs not rotated | Large `access.log` | `truncate -s 0` the active log; compress or move rotated logs | Daily rotation with compression; ship logs off the host |
| Deleted log still open | `df` full, `du` small, `lsof +L1` shows `(deleted)` | `nginx -s reopen` (no restart required) | logrotate `postrotate` signals NGINX; never `rm` an active log |
| Proxy cache / temp files | Large `/var/cache/nginx` | Clear the cache directory | `max_size` on `proxy_cache_path` |
| journald | `journalctl --disk-usage` in GB | `journalctl --vacuum-size=500M` | `SystemMaxUse=` |
| OS artifacts | apt cache, old kernels, core dumps | `apt clean`, `apt autoremove` | Scheduled cleanup |

The first two causes were reproduced on a 64 MB volume (`reproduce-disk-full.sh`):

```
traffic:          100% full, access.log = 64M
GET /          -> 200, but nothing logged
rm access.log  -> still 100%, du = 0
lsof +L1       -> nginx ... access.log (deleted)
nginx -s reopen-> 0%
```

`nginx -s reopen` is preferred over a restart, because restarting a load balancer drops active connections.

## Impact

| Area | Effect at 100% |
|---|---|
| Logging | NGINX continues serving but silently stops logging; no error is raised (observed in the reproduction) |
| Request handling | Request bodies larger than the in-memory buffer are written to disk and fail |
| Operations | apt and SSH logins can fail, slowing recovery |
| Blast radius | All upstream services behind the load balancer are affected |

## Prevention

| Control | Detail | Cost |
|---|---|---|
| Alerting | Disk and inode usage at 80%, plus a 24-hour fill forecast | Negligible |
| Central logging | S3 + Athena instead of CloudWatch Logs; at several GB/day, CloudWatch ingestion can exceed the VM cost | ~$0.023/GB-month vs ~$0.50/GB ingested |
| Log volume | Exclude health-check requests from access logs | None |
| Disk size | Increasing EBS size only delays recurrence | ~$0.08/GB-month (gp3) |

**Assumptions:** stock Ubuntu NGINX package with its default logrotate configuration. Without access to the VM, the causes are ranked by likelihood; step 2 identifies any cause not listed.
