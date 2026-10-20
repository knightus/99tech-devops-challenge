# Problem 4: CI/CD Pipelines for EC2 and S3

Two GitHub Actions pipelines: the backend API (the Problem 3 service) is built into a Docker image and deployed to EC2 through SSM, and the single-page frontend is published to S3 behind CloudFront. Both use short-lived AWS credentials (OIDC), deploy only after an approval gate, verify the result, and can be rolled back without rebuilding.

## Contents

- [Production Readiness Criteria](#production-readiness-criteria)
- [Backend Pipeline](#backend-pipeline)
- [Frontend Pipeline](#frontend-pipeline)
- [Rollback](#rollback)
- [Security](#security)
- [Repository Layout](#repository-layout)
- [Validation](#validation)
- [Cost](#cost)
- [Assumptions](#assumptions)
- [Out of Scope](#out-of-scope)

## Production Readiness Criteria

The criteria used to define "production ready", and how each is met.

| Criterion | Implementation |
|---|---|
| What runs in production is what CI tested | Image and SPA are built once in CI; servers never build |
| A bad deploy is caught by the pipeline, not users | Health check on the instance, public check after deploy |
| A bad deploy reverts automatically | Deploy script restores the previous image when the health check fails |
| Rollback is fast and needs no rebuild | Redeploy an earlier image tag or republish an archived release |
| No long-lived credentials | GitHub OIDC to AWS; no SSH keys, no stored AWS keys |
| Production changes are approved | `production` environment with required reviewers, enforced by the IAM trust policy |
| Deploys cannot overlap or be cut short | Per-environment concurrency group, never cancelled in progress |
| Dependencies stay patched | `npm audit` gate, actions pinned to commit SHAs, Dependabot |

## Backend Pipeline

`.github/workflows/backend.yml`. Pull requests run CI only; merges to `master` build and deploy.

![Backend pipeline](images/backend-pipeline.svg)

| Stage | Detail |
|---|---|
| CI | `npm ci`, `node --check`, `npm audit --omit=dev`; then the full Problem 3 stack is started and `verify.sh` injects 14 failure scenarios |
| Build | `docker build` of `src/problem3/api`, pushed to ECR with the commit SHA as an immutable tag |
| Deploy | SSM runs `deploy/deploy-backend.sh` on the instance: pull image, replace container, health-check `/status`, revert on failure |
| Verify | Public `/ready` check through the load balancer; failure prints the rollback instruction |

## Frontend Pipeline

`.github/workflows/frontend.yml`. The build is archived per release so any version can be republished.

![Frontend pipeline](images/frontend-pipeline.svg)

| Step | Detail |
|---|---|
| Cache headers | Hashed assets: `max-age=31536000, immutable`; `index.html` and `version.json`: `no-cache` |
| Publish order | Assets before `index.html`, so no client receives a page whose assets are not yet uploaded |
| No `--delete` | Clients that loaded the previous page still need its assets; an S3 lifecycle rule expires old objects after 30 days |
| Invalidation | Only `index.html` and `version.json`; hashed assets never change |
| Verification | `version.json` served by CloudFront must equal the deployed SHA, otherwise the job fails |

## Rollback

Both pipelines roll back through the same deploy path, so it is exercised on every release.

| Situation | Mechanism | Time |
|---|---|---|
| Backend unhealthy during deploy | `deploy-backend.sh` restarts the previous image automatically | ~30 s |
| Backend regression found later | Run `backend.yml` manually with an earlier image tag | ~2 min |
| Frontend regression | Run `frontend.yml` manually with an earlier release SHA | ~2 min |

Database migrations are not rolled back by the pipeline; schema changes must be backward compatible (expand, then contract).

## Security

Controls applied to the pipelines, consistent with Problem 5.

| Control | Detail |
|---|---|
| OIDC federation | Trust policy accepts only `repo:OWNER/REPO:environment:production` (deploy) and `ref:refs/heads/master` (image push) |
| Approval enforced by IAM | Without the environment approval, GitHub does not issue the `environment:production` token, so AWS refuses the role |
| No SSH | Deploys run through SSM Run Command; every command is recorded in CloudTrail; no inbound port is open |
| Least privilege | Backend role: push to one ECR repository, `SendCommand` only to instances tagged `Role=api`. Frontend role: write `releases/` and `live/` in one bucket, invalidate one distribution |
| Minimal token permissions | `contents: read` by default; `id-token: write` only on jobs that assume a role |
| Supply chain | Actions pinned to commit SHAs, kept current by Dependabot; `npm audit` blocks high-severity advisories |
| Configuration outside images | The instance reads `/etc/api/env`, provisioned from Secrets Manager at launch |

## Repository Layout

GitHub only runs workflows from the repository root, so the deliverables are paired with a root workflow that runs their AWS-independent parts.

| Path | Purpose |
|---|---|
| `src/problem4/.github/workflows/backend.yml` | Backend pipeline (deliverable) |
| `src/problem4/.github/workflows/frontend.yml` | Frontend pipeline (deliverable) |
| `src/problem4/.github/actions/` | CI steps shared by the deliverables and the root workflow |
| `src/problem4/.github/dependabot.yml` | Dependency updates for actions and npm |
| `src/problem4/deploy/deploy-backend.sh` | Runs on EC2: pull, swap, health-check, revert |
| `src/problem4/iam/` | OIDC trust policy, deploy role policies, instance policy |
| `src/problem4/frontend/` | Minimal Vite SPA |
| `.github/workflows/problem4-ci.yml` | Runs CI and `actionlint` on every pull request |

## Validation

What was executed, and what can only run with an AWS account.

| Item | Status |
|---|---|
| `actionlint` on all workflows | Passes, locally and in CI |
| Backend CI including 14 failure-injection tests | Runs on every pull request (root workflow) |
| Frontend build, audit and version stamp | Runs on every pull request (root workflow) |
| ECR push, SSM deploy, S3 publish, CloudFront invalidation | Implemented; skipped while `vars.AWS_ACCOUNT_ID` is unset, runs unchanged once configured |

## Cost

The pipelines add almost nothing to the Problem 1 infrastructure bill.

| Item | ~$/mo |
|---|---|
| ECR storage (~10 images × ~60 MB) | < 1 |
| S3 release archive (30-day lifecycle) | < 1 |
| CloudFront invalidations (first 1,000 paths/month free) | 0 |
| SSM Run Command | 0 |
| GitHub Actions minutes (public repository) | 0 |

## Assumptions

| Assumption | Reason |
|---|---|
| One EC2 instance runs the API container, with Docker and the SSM agent installed | Matches "an HTTP API deployed to EC2" |
| Postgres and Redis endpoints are provided through `/etc/api/env` | Configuration is not baked into the image |
| `master` is the production branch; pull requests run CI only | Single environment in scope |
| CloudFront origin path is `live/` and the bucket has a 30-day lifecycle rule on it | Required by the publish strategy |
| The ECR repository uses immutable tags | Guarantees a tag always means the same image |

## Out of Scope

| Left out | Impact | When to add |
|---|---|---|
| Staging environment | The deploy path is first exercised in production | First addition; the trust policy extends to a second environment |
| Zero-downtime backend deploys | A few seconds of errors during the container swap on a single instance | With 2 instances behind an ALB (~$30/mo), deploy one at a time |
| CodeDeploy | Not needed for one instance | At about 4+ instances |
| Database migration job | Requires a schema; none exists in this API | When the API owns migrations |
| End-to-end and canary tests, notifications | GitHub already notifies on failure | With real user traffic and metrics |
