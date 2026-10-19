# 99Tech DevOps Challenge

[![Problem 4 CI](https://github.com/knightus/99tech-devops-challenge/actions/workflows/problem4-ci.yml/badge.svg?branch=master)](https://github.com/knightus/99tech-devops-challenge/actions/workflows/problem4-ci.yml)

Solutions to the five problems of the 99Tech DevOps challenge. Each problem has a `SOLUTION.md`; cost is analyzed alongside every design decision.

## Contents

- [Solutions](#solutions)
- [Verifying the Hands-On Work](#verifying-the-hands-on-work)
- [Repository Layout](#repository-layout)

## Solutions

| # | Problem | Summary | Solution |
|---|---|---|---|
| 1 | Highly available trading system | Binance-style spot exchange on AWS at 500 req/s: three costed deployment options (~$1,160 to ~$2,960/month), deposits and withdrawals with KMS signing | [SOLUTION.md](src/problem1/SOLUTION.md) |
| 2 | NGINX load balancer at 99% disk | Troubleshooting runbook with ranked causes; the two most likely causes reproduced in a container | [SOLUTION.md](src/problem2/SOLUTION.md) |
| 3 | Unreliable Docker Compose platform | Seven defects found and fixed, each proven with failure injection; `verify.sh` passes 14/14 | [SOLUTION.md](src/problem3/SOLUTION.md) |
| 4 | CI/CD pipelines | GitHub Actions for EC2 (Docker, ECR, SSM) and S3/CloudFront, with OIDC, approval gate, automatic revert and rollback | [SOLUTION.md](src/problem4/SOLUTION.md) |
| 5 | Securing the platform | Problem 1 secured: 16 costed controls (~$490/month), priorities, accepted risks, open questions | [SOLUTION.md](src/problem5/SOLUTION.md) |

Problem 5 builds on Problem 1, and Problem 4 deploys the API fixed in Problem 3.

## Verifying the Hands-On Work

Problem 3 runs locally and checks its own fixes by injecting failures:

```bash
cd src/problem3
cp .env.example .env
docker compose up -d --build
./verify.sh                # NGINX_PORT=18080 ./verify.sh if port 8080 is in use
```

Problem 2's reproduction runs in a disposable container:

```bash
cd src/problem2
docker run --rm --tmpfs /var/log/nginx:size=64m \
  -v "$PWD/reproduce-disk-full.sh:/r.sh:ro" ubuntu:24.04 bash /r.sh
```

The same Problem 3 test suite runs on every pull request in [Problem 4 CI](.github/workflows/problem4-ci.yml), together with `actionlint` and the frontend build.

## Repository Layout

| Path | Content |
|---|---|
| `src/problem1/` | Architecture report |
| `src/problem2/` | Runbook and reproduction script |
| `src/problem3/` | Fixed stack, `verify.sh`, report |
| `src/problem4/` | Workflows, shared actions, deploy script, IAM policies, sample SPA, report |
| `src/problem5/` | Security report |
| `src/diagrams/` | Generator for the draw.io architecture diagrams (`python src/diagrams/build_diagrams.py`) |
| `.github/workflows/problem4-ci.yml` | Runs Problem 4's AWS-independent jobs, since GitHub ignores workflows under `src/` |
