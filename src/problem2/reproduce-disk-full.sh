#!/usr/bin/env bash
# Reproduces the two most likely causes of the full disk on a small scale.
# A 64 MB tmpfs on /var/log/nginx stands in for the VM's disk.
#
#   docker run --rm --tmpfs /var/log/nginx:size=64m \
#     -v "$PWD/reproduce-disk-full.sh:/r.sh:ro" ubuntu:24.04 bash /r.sh
set -u
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null && apt-get install -y -qq nginx lsof apache2-utils curl >/dev/null 2>&1
nginx

echo "### 1. Access log fills the disk"
df -h /var/log/nginx | tail -1
# Long URIs make each access log line ~3 KB, so the disk fills quickly.
pad=$(head -c 3000 /dev/zero | tr '\0' 'a')
ab -q -n 25000 -c 50 "http://127.0.0.1/$pad" >/dev/null 2>&1
df -h /var/log/nginx | tail -1
du -sh /var/log/nginx/* | sort -h
curl -s -o /dev/null -w "GET / while full -> %{http_code} (still serving, but no longer logging)\n" http://127.0.0.1/

echo
echo "### 2. Someone deletes the log, but nginx still holds it open"
rm /var/log/nginx/access.log
df -h /var/log/nginx | tail -1
du -sh /var/log/nginx
lsof +L1 2>/dev/null | awk 'NR==1 || /nginx/'

echo
echo "### Recovery: nginx reopens its log files and the space is freed"
nginx -s reopen
sleep 1
df -h /var/log/nginx | tail -1
