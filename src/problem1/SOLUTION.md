# Problem 1: Highly available trading system on AWS

A Binance-style spot exchange. 500 req/s is small, so the design spends money on correctness (no lost orders, no double-spent balances) and availability, not raw scale.

| | |
|---|---|
| Scope | Spot trading: place/cancel orders, matching, live order book + trades (WebSocket), balances, on-chain deposits and withdrawals |
| Out of scope | Futures, margin, KYC, fiat |
| Traffic | 500 req/s peak, ~150 average, ~10k WebSocket clients |
| Targets | p99 < 100 ms to accept an order · no lost or duplicate orders · survive losing an AZ |
| Region | `ap-southeast-1`, 3 AZs |

## Contents

- [How the system works](#how-the-system-works)
- [Deposits and withdrawals](#deposits-and-withdrawals)
- [Three ways to build it](#three-ways-to-build-it)
- [Option A: Lean (launch)](#option-a-lean-launch)
- [Option B: Balanced (target)](#option-b-balanced-target)
- [Option C: Resilient (regulated / high stakes)](#option-c-resilient-regulated--high-stakes)
- [Comparison](#comparison)
- [Shared cost: data out](#shared-cost-data-out)
- [Cost levers](#cost-levers)
- [How it stays up](#how-it-stays-up)
- [Latency budget (p99, order accepted)](#latency-budget-p99-order-accepted)
- [Services and alternatives](#services-and-alternatives)
- [Scaling plan](#scaling-plan)

## How the system works

When a user places an order, the API first sets aside the money in the database so it can't be spent twice. It then writes the order to an **order log**, a durable, ordered list of every order. A matching engine reads the log, matches buyers with sellers, and writes the resulting trades back out. Settlement updates balances from those trades, and the market data service pushes the live order book to users over WebSocket.

```mermaid
flowchart LR
  U[Users / bots] --> CF[CloudFront + WAF] --> ALB
  ALB --> API[Order API]
  ALB --> WS[WebSocket gateway]
  API -->|set money aside| DB[(PostgreSQL)]
  API -->|order| IN[[Order log]]
  IN --> ME[Matching engine<br/>active + standby]
  ME --> OUT[[Trades log]]
  OUT --> SET[Settlement] --> DB
  OUT --> MD[Market data] --> R[(Redis)] --> WS
  ME -.snapshot.-> S3[(S3)]
```

Every service runs on ECS Fargate with 3 copies across 3 AZs. There is one matching engine per trading pair, with a standby that reads the same log so it can take over if the active one fails.

## Deposits and withdrawals

This is how money moves on and off the exchange. It is not latency-sensitive (minutes are fine), but it is where an exchange can lose funds, so it is kept apart from trading. Problem 5 covers how it is secured.

```mermaid
flowchart LR
  CH[Blockchains] --> NP[Node provider]
  NP --> DW[Deposit watcher] -->|credit after N confirmations| DB[(RDS PostgreSQL)]
  API[Order API] -->|withdrawal: debit balance| DB
  API --> Q[[Withdrawal queue]]
  subgraph Custody account
    Q --> WS[Withdrawal signer] --> KMS[KMS key, secp256k1]
  end
  WS -->|broadcast| NP --> CH
```

| Part | What it does | Why this way |
|---|---|---|
| Node provider | Reads and sends blockchain transactions | Running our own nodes is ~$300/mo per chain plus ops; a provider is cheaper at this size |
| Deposit watcher | Credits a deposit after N confirmations | Keyed on transaction hash, so a deposit can never be credited twice |
| Withdrawal queue | Holds approved withdrawals until signed | Durable: a signer outage delays withdrawals, never loses them |
| Withdrawal signer | Signs and broadcasts in a separate AWS account | Production can only add to the queue, never sign |
| KMS secp256k1 key | Signing key for the hot wallet | Key stays in AWS's FIPS 140-2 L3 hardware; ~$20/mo vs ~$2,100/mo for 2 CloudHSM units |
| Hot / cold split | Only a small share of funds is online | A full compromise can only reach the hot wallet |

## Three ways to build it

The services above stay the same. What changes is how the order log is stored, how fast the database fails over, and whether there is a backup region. More resilience costs more, so I priced three versions.

## Option A: Lean (launch)

The order log is a table in PostgreSQL. No extra systems to run, so it's the cheapest way to launch.

| Component | Choice | ~$/mo |
|---|---|---|
| Compute | Fargate, 13 small tasks | 315 |
| Order log | Ordered Postgres table (no Kafka) | 0 |
| Database | RDS PostgreSQL Multi-AZ, m7g.large | 275 |
| Cache | Redis t4g.medium ×2 | 95 |
| Edge | WAF + ALB | 280 |
| Network / logs | 1 NAT, CloudWatch | 125 |
| Wallet | Deposit + withdrawal services, node provider, KMS | 260 |
| **Total** | on-demand / 1-yr commitments | **1,350 / 1,160** |

| Pros | Cons |
|---|---|
| Cheapest, fewest moving parts | Every order is a DB write: tops out around 10x traffic |
| Recovery is exact (replay the table) | Engine recovery takes minutes, not seconds |

## Option B: Balanced (target)

The order log moves to Kafka (Amazon MSK), which is built for this job. The standby engine takes over in seconds, and the system can grow about 100x.

| Component | Choice | ~$/mo |
|---|---|---|
| Compute | Fargate, 13 small tasks | 315 |
| Order log | MSK, 3× m7g.large | 465 |
| Database | RDS PostgreSQL Multi-AZ, m7g.large | 275 |
| Cache | Redis t4g.medium ×2 | 95 |
| Edge | WAF + ALB | 280 |
| Network / logs | 1 NAT, CloudWatch | 125 |
| Wallet | Deposit + withdrawal services, node provider, KMS | 260 |
| **Total** | on-demand / 1-yr commitments | **1,810 / 1,620** |

| Pros | Cons |
|---|---|
| Kafka adds ~5 ms; engine fails over in seconds | MSK is the biggest line and has no reserved pricing |
| Grows to ~100x by adding partitions | More to operate than A |

## Option C: Resilient (regulated / high stakes)

Option B plus faster database failover (Aurora) and a standby copy in a second region.

| Component | Choice | ~$/mo |
|---|---|---|
| Compute | Fargate, 13 small tasks | 315 |
| Order log | MSK + cross-region replication | 650 |
| Database | Aurora writer + reader, Global Database | 760 |
| Cache | Redis Multi-AZ | 235 |
| Edge | WAF + ALB | 280 |
| Network / logs | 3 NAT, CloudWatch | 255 |
| Second region | Pilot light (replicas only, no compute) | 455 |
| Wallet | Same as B + a second node provider for failover | 460 |
| **Total** | on-demand / 1-yr commitments | **3,410 / 2,960** |

| Pros | Cons |
|---|---|
| AZ failover < 30 s, region failover ~15 min | ~2x the cost of B |
| < 1 min of data lost if a region goes down | Global DB and replication add operational work |

## Comparison

What each option costs, and what it buys you when things fail.

```mermaid
xychart-beta
  title "Monthly cost, $ (1-yr commitments)"
  x-axis ["A Lean", "B Balanced", "C Resilient"]
  y-axis "USD" 0 --> 3500
  bar [1160, 1620, 2960]
```

| | A | B | C |
|---|---|---|---|
| Lose 1 AZ | 1-2 min cancel-only | 1-2 min cancel-only | < 30 s |
| Lose the region | hours | hours | ~15 min |
| Data lost (region) | minutes | minutes | < 1 min |
| Engine failover | minutes | seconds | seconds |
| Grows to | ~10x | ~100x | ~100x |

**Recommendation:** launch on A. Move to B before traffic grows about 10x; the change is small, because the engine just reads Kafka instead of a table. Move to C only when a region outage would cost more than about $1.5k/month.

## Shared cost: data out

Same for every option, and bigger than all of them.

| Market data per client | 10k clients, data/mo | ~$/mo |
|---|---|---|
| 2 KB/s, full book updates | 50 TB | 5,000 |
| Deltas + compressed frames (~70% smaller) | 15 TB | 1,500 |

## Cost levers

Ways to cut the bill in any option, and what each one costs you.

| Lever | Saves | Catch |
|---|---|---|
| 1-yr Savings Plan + RDS/Redis reservations | ~12-17% | 1-year commitment (MSK has no reserved pricing) |
| 1 NAT instead of 3 | ~$90/mo | Outbound internet lost if that AZ fails; trading unaffected |
| S3 gateway endpoint | NAT data charges | None, it's free |
| Auto-scaling | Little now | Min 3 tasks for HA already covers peak; matters at growth |
| Fargate Spot | ~70% on batch work | Interruptible: never API or engine |
| Non-prod off at night | ~60-70% of non-prod | None |

## How it stays up

The failures that matter for an exchange, and how the design handles each (described for Option B).

| Risk | Handling |
|---|---|
| Task / AZ failure | 3 tasks across 3 AZs; 2 can carry peak |
| Engine crash | Standby replays the same log; snapshot + offset = exact recovery |
| Two engines active | Lease picks the active one; Kafka fencing rejects writes from a stale one |
| Bad order message | Engine emits `rejected`, never crashes; unprocessable → dead-letter topic + alert |
| Retries / duplicates | Client order ID; settlement keyed on trade ID |
| DB failover | API switches to cancel-only for 1-2 min |
| Traffic spike | Kafka buffers; scale on consumer lag, not CPU |
| Node provider outage | Withdrawals wait in the queue; deposits are credited once it's back (C: second provider) |
| Withdrawal retried | Idempotent on withdrawal ID; one nonce per withdrawal, so a retry never pays twice |

## Latency budget (p99, order accepted)

Time for an order to be accepted (`202`), step by step, for Option B.

| Step | ms |
|---|---|
| ALB | 2 |
| API logic | 3 |
| Balance reserve (Postgres) | 5-10 |
| Kafka write, 3 AZs | 5-15 |
| **Total** | **~30** (target 100) |

## Services and alternatives

Each main choice and what it beat.

| Choice | Instead of | Why |
|---|---|---|
| ECS Fargate | EKS | No node patching; EKS adds $73/mo + upgrades we don't need yet |
| MSK | Kinesis / SQS | Kinesis adds 70-200 ms per hop; SQS deletes messages, so no replay |
| RDS PostgreSQL | DynamoDB / Aurora | Ledger needs ACID; Aurora's faster failover costs ~30% more (Option C) |
| ALB WebSocket | API Gateway WebSocket | API Gateway bills per message; market data is thousands/s |
| WAF per API key | Per IP only | Abuse is one bot with valid keys spamming orders |
| KMS secp256k1 | CloudHSM / MPC provider | Same hardware-backed keys for ~$20 vs ~$2,100/mo; MPC adds insurance but costs thousands |
| Node provider | Own nodes | ~$200/mo vs ~$300/mo per chain plus syncing and upgrades |

## Scaling plan

What changes as traffic grows past today's setup.

| Traffic | Change |
|---|---|
| ~5k req/s | Move to B; read replicas for history; WebSocket on its own ALB |
| ~50k req/s | Shard engines by symbol; in-memory risk check instead of DB write; Aurora; consider EKS |
| Always | One writer per symbol; multi-region active-active for reads only |

Prices are approximate `ap-southeast-1` list prices, and the traffic numbers are estimates. With real volumes I'd redo the cost tables first. Security is in Problem 5.
