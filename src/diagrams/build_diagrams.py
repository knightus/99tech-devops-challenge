"""Build the architecture diagrams for Problems 1 and 5 as .drawio files.

    python src/diagrams/build_diagrams.py

Each file is written next to the report that uses it (src/problemN/images/).
Exported SVGs sit beside the .drawio sources.
"""
from pathlib import Path

from drawio import Drawing

ROOT = Path(__file__).resolve().parents[1]

# Column x positions for the 4 icon columns inside the VPC.
C1, C2, C3, C4 = 150, 330, 510, 690


def core(d, mark=None, custody=(230, 560)):
    """Shared Option A layout. `mark` maps an icon key to 'added'/'changed' (Problem 5)."""
    mark = mark or {}
    m = lambda k: mark.get(k)  # noqa: E731
    n = {}

    n["users"] = d.icon("Traders / API clients", "users", "general", 60, 140)

    d.group("Edge", "plain", 200, 110, 500, 130)
    n["dns"] = d.icon("Route 53", "route_53", "network", C1 + 80, 140)
    n["cdn"] = d.icon("CloudFront + WAF\nShield Standard", "cloudfront", "network", C2 + 80, 140, mark=m("cdn"))

    d.group("Production account, ap-southeast-1", "account", 40, 290, 1180, 830)
    d.group("VPC, 3 Availability Zones", "vpc", 60, 330, 800, 770)

    d.group("Public subnets", "public", 80, 370, 760, 130)
    n["alb"] = d.icon("Application Load Balancer", "elastic_load_balancing", "network", C2, 400)
    n["nat"] = d.icon("NAT gateway", "nat_gateway", "network", C4, 400, resource=True)

    d.group("Private app subnets: ECS Fargate", "private", 80, 530, 760, 300)
    n["api"] = d.icon("Order API", "fargate", "compute", C1, 570, mark=m("api"))
    n["ws"] = d.icon("WebSocket gateway", "fargate", "compute", C2, 570)
    n["dep"] = d.icon("Deposit watcher", "fargate", "compute", C4, 570)
    n["eng"] = d.icon("Matching engine\nactive + standby", "fargate", "compute", C1, 720)
    n["set"] = d.icon("Settlement", "fargate", "compute", C2, 720)
    n["md"] = d.icon("Market data", "fargate", "compute", C3, 720)

    d.group("Private data subnets", "private", 80, 860, 760, 220)
    n["rds"] = d.icon("RDS PostgreSQL Multi-AZ\nledger + order log", "rds", "database", C1, 920, mark=m("rds"))
    n["redis"] = d.icon("ElastiCache Redis", "elasticache", "database", C3, 920)

    d.group("Shared services", "plain", 890, 330, 310, 380)
    n["s3"] = d.icon("S3\nsnapshots, archive", "s3", "storage", 930, 370, mark=m("s3"))
    n["ddb"] = d.icon("DynamoDB\nengine lease", "dynamodb", "database", 1080, 370)
    n["sm"] = d.icon("Secrets Manager", "secrets_manager", "security", 930, 490)
    n["ecr"] = d.icon("ECR", "ecr", "containers", 1080, 490)
    n["cw"] = d.icon("CloudWatch", "cloudwatch_2", "management", 930, 610)

    d.group("Custody account", "account", 1260, 290, custody[0], custody[1])
    n["sqs"] = d.icon("SQS FIFO\nwithdrawals", "sqs", "integration", 1345, 360)
    n["sig"] = d.icon("Withdrawal signer", "fargate", "compute", 1345, 520)
    n["kms"] = d.icon("KMS key\nsecp256k1", "key_management_service", "security", 1345, 680, mark=m("kms"))

    n["node"] = d.icon("Blockchain\nnode provider", "internet", "general", 1345, 960)

    # Request path
    d.edge(n["users"], n["dns"], "HTTPS")
    d.edge(n["dns"], n["cdn"])
    d.edge(n["cdn"], n["alb"], points=[(C2 + 108, 330), (C2 + 28, 330)])
    d.edge(n["alb"], n["api"], exit=(0.25, 1), points=[(C2 + 14, 530), (C1 + 28, 530)])
    d.edge(n["alb"], n["ws"])
    # Trading data path
    d.edge(n["api"], n["rds"], "reserve + order", exit=(0.25, 1), entry=(0.25, 0), points=[(C1 + 14, 690), (C1 - 30, 690), (C1 - 30, 880), (C1 + 14, 880)])
    d.edge(n["rds"], n["eng"], "orders", kind="data", exit=(0.75, 0), entry=(0.75, 1))
    d.edge(n["eng"], n["set"], "trades", kind="data")
    d.edge(n["set"], n["rds"], kind="data", exit=(0.5, 1), entry=(1, 0.5), points=[(C2 + 28, 948)])
    d.edge(n["eng"], n["md"], kind="data", exit=(0.5, 0), entry=(0.5, 0), points=[(C1 + 28, 700), (C3 + 28, 700)])
    d.edge(n["md"], n["redis"], kind="data")
    d.edge(n["redis"], n["ws"], kind="data", exit=(1, 0.5), entry=(1, 0.5), points=[(C4 - 20, 948), (C4 - 20, 598)])
    # Deposits and withdrawals
    d.edge(n["dep"], n["rds"], "credit", exit=(0.5, 1), entry=(1, 0.25), points=[(C4 + 28, 934)])
    d.edge(n["dep"], n["nat"], kind="optional", exit=(0.5, 0), entry=(0.5, 1))
    d.edge(n["nat"], n["node"], kind="optional", exit=(1, 0.5), entry=(0, 0.5), points=[(1235, 428), (1235, 988)])
    d.edge(n["api"], n["sqs"], "withdrawal", exit=(0.5, 0), entry=(0, 0.5), points=[(C1 + 28, 545), (1240, 545), (1240, 388)])
    d.edge(n["sqs"], n["sig"])
    d.edge(n["sig"], n["kms"], "sign")
    d.edge(n["sig"], n["node"], "broadcast", exit=(1, 0.5), entry=(1, 0.5), points=[(1440, 548), (1440, 988)])
    return n


def option_a():
    d = Drawing(
        "Option A: Cost-Optimized",
        "Single region, 3 Availability Zones. The order log is a PostgreSQL table; withdrawals are signed in a separate custody account.",
    )
    core(d)
    d.legend(40, 1150, [("request", "Request"), ("data", "Order / trade data"), ("optional", "Outbound via NAT")])
    d.save(ROOT / "problem1/images/option-a-aws.drawio")


def options_b_c():
    d = Drawing(
        "Options B and C: changes from Option A",
        "Highlighted components are added or changed; everything else is identical to Option A.",
    )
    d.group("Option B: order log moves to Amazon MSK", "plain", 40, 110, 700, 330)
    api = d.icon("Order API", "fargate", "compute", 80, 220)
    msk = d.icon("Amazon MSK\norders + trades topics", "managed_streaming_for_kafka", "network", 300, 220, mark="added")
    eng = d.icon("Matching engine", "fargate", "compute", 520, 160)
    sett = d.icon("Settlement", "fargate", "compute", 520, 300)
    rds = d.icon("RDS PostgreSQL\nbalances only", "rds", "database", 300, 360, mark="changed")
    d.edge(api, msk, "order")
    d.edge(msk, eng, kind="data", exit=(1, 0.25), entry=(0, 0.5))
    d.edge(eng, msk, "trades", kind="data", exit=(0.5, 1), entry=(1, 0.75), points=[(548, 262)])
    d.edge(msk, sett, kind="data", exit=(1, 1), entry=(0, 0.5), points=[(356, 328)])
    d.edge(sett, rds, exit=(0.5, 1), entry=(1, 0.5), points=[(548, 388)])
    d.edge(api, rds, "reserve", exit=(0.5, 1), entry=(0, 0.5), points=[(108, 388)])

    d.group("Option C: adds to Option B", "plain", 780, 110, 700, 330)
    d.group("Primary region", "region", 800, 150, 300, 270)
    # Each primary service sits directly opposite its DR copy, so replication runs straight across.
    d.icon("Redis Multi-AZ", "elasticache", "database", 840, 190, mark="changed")
    msk1 = d.icon("Amazon MSK", "managed_streaming_for_kafka", "network", 980, 190)
    d.icon("NAT gateway x3", "nat_gateway", "network", 840, 320, mark="changed", resource=True)
    aur = d.icon("Aurora PostgreSQL\nwriter + reader", "aurora", "database", 980, 320, mark="changed")
    d.group("DR region, pilot light", "region", 1160, 150, 300, 270, highlight=True)
    msk2 = d.icon("MSK replica", "managed_streaming_for_kafka", "network", 1200, 190, mark="added")
    d.icon("S3 replica", "s3", "storage", 1340, 190, mark="added")
    aur2 = d.icon("Aurora Global\nsecondary", "aurora", "database", 1200, 320, mark="added")
    d.icon("Second node\nprovider", "internet", "general", 1340, 320, mark="added")
    d.edge(msk1, msk2, "MSK Replicator", kind="data")
    d.edge(aur, aur2, "Global Database", kind="data")
    d.legend(40, 470, [("request", "Request"), ("data", "Data / replication")])
    d.text("mk", "Green border: added. Amber border: changed.", 280, 480, 400, 20, size=11, color="#545B64")
    d.save(ROOT / "problem1/images/options-b-c-changes.drawio")


def wallet_flow():
    d = Drawing(
        "Deposit and Withdrawal Flow",
        "Production can only enqueue a withdrawal. Signing happens in the custody account; the key never leaves KMS.",
    )
    chain = d.icon("Blockchains", "internet", "general", 60, 260)
    node = d.icon("Node provider", "internet", "general", 240, 260)
    d.group("Production account", "account", 400, 110, 420, 330)
    dep = d.icon("Deposit watcher", "fargate", "compute", 450, 170)
    api = d.icon("Order API", "fargate", "compute", 450, 330)
    db = d.icon("PostgreSQL\nledger", "rds", "database", 690, 250)
    d.group("Custody account", "account", 880, 110, 560, 330)
    q = d.icon("SQS FIFO\nwithdrawal queue", "sqs", "integration", 930, 330)
    sig = d.icon("Withdrawal signer", "fargate", "compute", 1110, 330)
    kms = d.icon("KMS key\nsecp256k1", "key_management_service", "security", 1300, 330)
    d.edge(chain, node, kind="data")
    d.edge(node, dep, "1. new deposit", kind="data", exit=(0.5, 0), entry=(0, 0.5), points=[(268, 198)])
    d.edge(dep, db, "2. credit after N confirmations", exit=(1, 0.5), entry=(0.5, 0), points=[(718, 198)])
    d.edge(api, db, "3. debit balance", exit=(1, 0.5), entry=(0.5, 1), points=[(718, 358)])
    d.edge(api, q, "4. enqueue only", exit=(0.5, 1), entry=(0.5, 1), points=[(478, 470), (958, 470)])
    d.edge(q, sig, "5")
    d.edge(sig, kms, "6. sign")
    d.edge(sig, node, "7. broadcast", exit=(0.5, 0), entry=(0.5, 0), points=[(1138, 90), (268, 90)])
    d.legend(40, 520, [("request", "Request"), ("data", "Blockchain data")])
    d.save(ROOT / "problem1/images/deposit-withdrawal-flow.drawio")


def secured():
    d = Drawing(
        "Secured Architecture (Problem 5)",
        "Option A layout with security controls. Green border: added control. Amber border: changed component.",
    )
    mark = {"cdn": "changed", "api": "changed", "rds": "changed", "s3": "changed", "kms": "changed"}
    n = core(d, mark, custody=(400, 640))
    # Added controls placed beside the components they protect.
    dnsfw = d.icon("Route 53 DNS Firewall\ndomain allowlist", "route_53", "network", C3, 400, mark="added")
    nfw = d.icon("Network Firewall\nnode provider only", "network_firewall", "security", 1345, 830, mark="added")
    pol = d.icon("Policy engine\nlimits, allowlist,\n2-person approval", "fargate", "compute", 1530, 440, mark="added")
    rec = d.icon("Reconciliation\nauto-halt", "fargate", "compute", 1530, 640, mark="added")
    gd = d.icon("GuardDuty +\nSecurity Hub", "guardduty", "security", 1080, 610, mark="added")
    d.group("Security account", "account", 1260, 1150, 230, 150)
    logs = d.icon("CloudTrail + logs\nS3 Object Lock", "cloudtrail", "management", 1345, 1200, mark="added")
    d.edge(n["dep"], dnsfw, kind="optional", exit=(0, 0.5), entry=(0.5, 1), points=[(C3 + 28, 598)])
    d.edge(n["sqs"], pol, "check", kind="request", exit=(1, 0.5), entry=(0.5, 0), points=[(1558, 388)])
    d.edge(rec, n["node"], "verify balances", kind="optional", exit=(0.5, 1), entry=(1, 0.25))
    d.edge(n["sig"], nfw, kind="optional", exit=(0, 0.5), entry=(0, 0.5), points=[(1310, 548), (1310, 858)])
    d.edge(n["cw"], logs, "write-only", kind="optional", exit=(0.5, 1), entry=(0, 0.5), points=[(958, 1228)])
    d.legend(40, 1150, [("request", "Request"), ("data", "Order / trade data"), ("optional", "Control / log path")])
    d.save(ROOT / "problem5/images/secured-architecture.drawio")


if __name__ == "__main__":
    for folder in ("problem1/images", "problem5/images"):
        (ROOT / folder).mkdir(parents=True, exist_ok=True)
    option_a()
    options_b_c()
    wallet_flow()
    secured()
    print("written")
