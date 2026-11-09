#!/usr/bin/env python3
"""Seed one demo conference through the public HTTP API.

Talks go in via POST /confirm-schedule (organizer key), attendees via POST /save-user-data.
Elasticsearch is never touched directly. Stdlib only; Python 3.11+.

    python3 scripts/seed_demo.py --base-url https://wearedevs.cnh.radarhq.io/api
    python3 scripts/seed_demo.py --dry-run          # print payload shapes, no network

ORGANIZER_API_KEY is read from the environment or from `.env` in the repo root. Attendee
bearer tokens are written to a gitignored, mode-600 file (default `.demo-tokens.json`) so a
presenter can log in as a fake attendee. Re-running is idempotent: talks carry stable
`talk_id`s so confirm-schedule overwrites them, and attendees whose token is already in the
tokens file are updated in place instead of duplicated. Nothing secret is ever printed.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://wearedevs.cnh.radarhq.io/api"
DEFAULT_TOKENS_FILE = REPO_ROOT / ".demo-tokens.json"

CONFERENCE_ID = "cnh-slc-2026"
CONFERENCE_NAME = "Cloud Native Hackathon @ KubeCon NA 2026"
# Nov 9 2026, Salt Lake City. DST ended Nov 1, so America/Denver is MST (-07:00).
DAY = "2026-11-09"
TZ = "-07:00"


def at(hhmm: str) -> str:
    return f"{DAY}T{hhmm}:00{TZ}"


def talk(
    num: int,
    title: str,
    start: str,
    end: str,
    room: str,
    track: str,
    speakers: list[str],
    abstract: str,
) -> dict[str, Any]:
    return {
        "talk_id": f"{CONFERENCE_ID}-t{num:02d}",
        "title": title,
        "start_time": at(start),
        "end_time": at(end),
        "room": room,
        "track": track,
        "speakers": speakers,
        "abstract": abstract,
    }


# Speakers are invented; no real people.
TALKS: list[dict[str, Any]] = [
    talk(
        1,
        "Opening Keynote: The Platform Is the Product",
        "10:00", "10:40", "Main", "Platform Engineering",
        ["Priyanka Oyelaran-Voss"],
        "Platform teams fail when they ship infrastructure instead of a product. This keynote "
        "walks through how a 400-engineer org rebuilt its internal developer platform around "
        "golden paths, self-service namespaces, and measurable developer experience. Expect "
        "concrete metrics on lead time, onboarding, and the cost of abstractions nobody asked for.",
    ),
    talk(
        2,
        "OpenTelemetry End to End: Traces, Metrics, and Logs Without the Glue Code",
        "10:50", "11:30", "Main", "Observability",
        ["Tomasz Ferreira-Blight"],
        "Instrumenting a polyglot microservice fleet usually means three agents, two collectors, "
        "and a pile of YAML. This session shows a single OpenTelemetry Collector pipeline that "
        "correlates traces, metrics, and logs by resource attributes and exports them to any "
        "backend. We cover sampling strategies, semantic conventions, and how to keep "
        "cardinality from eating your bill.",
    ),
    talk(
        3,
        "Kubernetes Supply Chain Security: SBOMs, Sigstore, and Admission Policy",
        "10:50", "11:30", "Room A", "Security",
        ["Yuki Abernathy-Mensah"],
        "Signing container images is only useful if the cluster refuses to run unsigned ones. "
        "We build a pipeline that generates SBOMs with Syft, signs images with Cosign and "
        "keyless Sigstore, and enforces provenance at admission with Kyverno policies. "
        "Includes the failure modes we hit rolling this out across 60 clusters.",
    ),
    talk(
        4,
        "Hybrid Search on Kubernetes: BM25 Meets Vectors in Elasticsearch",
        "10:50", "11:30", "Room B", "Search",
        ["Nadia Kowalczyk-Reyes"],
        "Pure vector search misses exact matches and pure keyword search misses meaning. This "
        "talk shows how to combine BM25 and dense embeddings with reciprocal rank fusion and "
        "linear retrievers in Elasticsearch, deployed with the ECK operator. We compare "
        "semantic_text with hand-rolled embedding pipelines on latency, relevance, and ops burden.",
    ),
    talk(
        5,
        "eBPF for Mortals: Observability Without Sidecars",
        "11:40", "12:20", "Main", "eBPF",
        ["Dmitri Okonkwo-Halvorsen"],
        "eBPF lets you watch syscalls, network flows, and HTTP requests from the kernel without "
        "touching application code or injecting sidecars. We walk through building a small "
        "tracing tool with libbpf and CO-RE, then compare it to Cilium Hubble and Pixie for "
        "production use. You will leave knowing when eBPF is the right hammer and when it is not.",
    ),
    talk(
        6,
        "GitOps at Scale: Argo CD ApplicationSets Across 200 Clusters",
        "11:40", "12:20", "Room A", "GitOps",
        ["Soren Adebayo-Lindqvist"],
        "One Argo CD instance per cluster does not scale, and one for everything is a blast "
        "radius problem. This session covers the hub-and-spoke topology, ApplicationSet "
        "generators driven by cluster labels, progressive sync waves, and how we handle secrets "
        "and drift detection. Real numbers on reconcile latency and repo-server memory included.",
    ),
    talk(
        7,
        "Serving LLMs on Kubernetes: GPU Scheduling, vLLM, and Autoscaling on Queue Depth",
        "11:40", "12:20", "Room B", "AI/ML on K8s",
        ["Amara Lindgren-Castellanos"],
        "Running inference on Kubernetes means fighting GPU fragmentation, slow cold starts, and "
        "autoscalers that only understand CPU. We deploy vLLM behind KServe, use the NVIDIA "
        "device plugin and DRA for allocation, and autoscale on request queue depth with KEDA. "
        "Includes a cost comparison against managed inference endpoints.",
    ),
    talk(
        8,
        "Lunch and Hallway Track",
        "12:20", "13:20", "Main", "Community",
        [],
        "Grab food and find the people whose talks you want to argue about. The attendee "
        "matching board in the lobby pairs you with others working on similar problems. "
        "Sponsors have tables along the east wall.",
    ),
    talk(
        9,
        "SLOs That Engineers Actually Use: Error Budgets with Prometheus and Dash0",
        "13:20", "14:00", "Main", "Observability",
        ["Ingrid Nakamura-Osei"],
        "Most SLO dashboards are built once and never looked at again. This talk shows how to "
        "define SLIs from RED metrics, compute multi-window burn rates in PromQL, and wire "
        "alerts so on-call only wakes up when the budget is genuinely at risk. We share the "
        "templates we use across 40 services and the three SLOs we deleted because nobody cared.",
    ),
    talk(
        10,
        "Zero Trust Networking with Cilium: Identity-Based Policy and Mutual TLS",
        "13:20", "14:00", "Room A", "Security",
        ["Rafael Oduya-Brennan"],
        "IP-based network policy breaks the moment pods reschedule. Cilium attaches identity to "
        "workloads and enforces L3 through L7 policy in eBPF, with optional mutual "
        "authentication using SPIFFE identities. We demo policy authoring, observe flows with "
        "Hubble, and discuss the migration path from Calico and from a service mesh.",
    ),
    talk(
        11,
        "RAG Pipelines on Kubernetes: Chunking, Embeddings, and Retrieval Quality",
        "13:20", "14:00", "Room B", "AI/ML on K8s",
        ["Chen Wakefield-Adeyemi"],
        "Retrieval-augmented generation lives or dies on retrieval quality, not on the model. "
        "We build an ingestion pipeline with Argo Workflows that chunks documents, generates "
        "embeddings, and indexes them in Elasticsearch, then measure recall with a golden "
        "question set. Covers hybrid retrieval, reranking, and when a bigger context window is "
        "the wrong answer.",
    ),
    talk(
        12,
        "Crossplane and Internal Developer Portals: Self-Service Infra Done Right",
        "14:10", "14:50", "Main", "Platform Engineering",
        ["Fatima Bjornstad-Achebe"],
        "Developers want a database, not a Terraform module. We use Crossplane compositions to "
        "expose opinionated cloud resources as Kubernetes APIs and surface them through a "
        "Backstage portal with scaffolder templates. The talk covers composition versioning, "
        "RBAC boundaries, and how to avoid rebuilding a worse cloud console.",
    ),
    talk(
        13,
        "Continuous Profiling in Production with eBPF and Parca",
        "14:10", "14:50", "Room A", "eBPF",
        ["Leila Thornquist-Mbeki"],
        "Metrics tell you a service is slow; profiles tell you which function. Continuous "
        "profiling with eBPF samples every process on the node at negligible overhead, no "
        "agents in your containers. We show how to deploy Parca, read flame graphs across "
        "deployments, and connect profiles to traces so you can go from a slow span to a hot loop.",
    ),
    talk(
        14,
        "Vector Search Performance: HNSW Tuning, Quantization, and Memory Budgets",
        "14:10", "14:50", "Room B", "Search",
        ["Marcus Olufemi-Haugen"],
        "A hundred million vectors do not fit in RAM for free. This deep dive covers HNSW graph "
        "parameters, int8 and binary quantization, and how to size Elasticsearch data nodes for "
        "kNN workloads on Kubernetes. We benchmark recall against latency and show what breaks "
        "when you get the memory math wrong.",
    ),
    talk(
        15,
        "Progressive Delivery with Argo Rollouts: Canaries, Analysis, and Automatic Rollback",
        "15:00", "15:40", "Main", "GitOps",
        ["Hana Petrosyan-Delacroix"],
        "Deploying to 100 percent of traffic and watching dashboards is not a strategy. Argo "
        "Rollouts lets you shift traffic in steps and gate each step on Prometheus queries or "
        "OpenTelemetry metrics. We cover AnalysisTemplates, integration with Istio and Gateway "
        "API, and how automated rollback changed our incident count.",
    ),
    talk(
        16,
        "Secrets Management on Kubernetes: External Secrets, Vault, and Workload Identity",
        "15:00", "15:40", "Room A", "Security",
        ["Kwame Lindholm-Sato"],
        "Secrets in git, even encrypted, are a liability. This session compares External "
        "Secrets Operator with Vault Agent injection and cloud workload identity federation, "
        "and shows how to rotate credentials without restarting pods. We finish with an audit "
        "checklist for finding the secrets you forgot you had.",
    ),
    talk(
        17,
        "Fine-Tuning and Training Jobs on Kubernetes with Kubeflow and Volcano",
        "15:00", "15:40", "Room B", "AI/ML on K8s",
        ["Beatriz Nkemelu-Strand"],
        "Training jobs need gang scheduling, checkpointing, and fair GPU sharing between teams, "
        "none of which the default scheduler provides. We run distributed PyTorch jobs with "
        "Kubeflow Training Operator and Volcano queues, handle spot preemption with "
        "checkpoint-restore, and track experiments with MLflow. Includes a cluster cost breakdown.",
    ),
    talk(
        18,
        "Debugging Kubernetes Networking: From DNS Timeouts to Dropped Packets",
        "15:50", "16:30", "Main", "Observability",
        ["Oluwaseun Marchetti-Vang"],
        "Intermittent DNS failures and mysterious connection resets eat days of engineering "
        "time. This talk is a systematic debugging method: CoreDNS metrics, conntrack tables, "
        "kube-proxy versus eBPF datapaths, and when to reach for tcpdump versus Hubble. Every "
        "example comes from a real postmortem.",
    ),
    talk(
        19,
        "Multi-Tenancy Without Tears: Namespaces, vCluster, and Hierarchical Quotas",
        "15:50", "16:30", "Room A", "Platform Engineering",
        ["Elena Oyibo-Rasmussen"],
        "One cluster per team is expensive; one namespace per team is leaky. We compare "
        "namespace-based tenancy with Hierarchical Namespace Controller, virtual clusters with "
        "vCluster, and full cluster isolation on cost, security, and operational load. Comes with "
        "a decision matrix you can take back to your platform team.",
    ),
    talk(
        20,
        "Closing Panel: What Cloud Native Looks Like in 2030",
        "16:40", "17:30", "Main", "Community",
        ["Priyanka Oyelaran-Voss", "Dmitri Okonkwo-Halvorsen", "Amara Lindgren-Castellanos"],
        "Our speakers debate where the ecosystem is heading: will AI agents operate clusters, "
        "does eBPF replace the service mesh, and is Kubernetes becoming invisible plumbing? "
        "Audience questions drive the second half. Bring your hottest take.",
    ),
]


def attendee(
    name: str,
    bio: str,
    interests: list[str],
    *,
    email: str | None = None,
    linkedin_url: str | None = None,
    discovery_opt_in: bool = True,
    blockout_times: list[dict[str, str]] | None = None,
    resume_text: str | None = None,
    resume_public: bool = False,
) -> dict[str, Any]:
    handle = name.lower().replace(" ", ".")
    payload: dict[str, Any] = {
        "conference_id": CONFERENCE_ID,
        "name": name,
        "email": email or f"{handle}@example.com",
        "bio": bio,
        "interests": interests,
        "blockout_times": blockout_times or [],
        "discovery_opt_in": discovery_opt_in,
        "resume_public": resume_public,
    }
    if linkedin_url:
        payload["linkedin_url"] = linkedin_url
    if resume_text:
        payload["resume_text"] = resume_text
    return payload


# Clearly fake names; example.com emails; no real people.
ATTENDEES: list[dict[str, Any]] = [
    attendee(
        "Zephyr Quillfeather",
        "Platform engineer at a mid-size fintech. I run our internal developer platform on "
        "Kubernetes with Argo CD and Crossplane and spend most of my time making golden paths "
        "developers actually follow. Trying to figure out whether Backstage is worth the upkeep.",
        ["platform engineering", "gitops", "argo cd", "crossplane", "backstage", "developer experience"],
        linkedin_url="https://www.linkedin.com/in/zephyr-quillfeather-demo",
        resume_text=(
            "Zephyr Quillfeather. Staff Platform Engineer, 2022-present: built a multi-tenant "
            "Kubernetes platform serving 300 developers; introduced Argo CD ApplicationSets, "
            "Crossplane compositions for RDS and S3, and a Backstage portal. Previously SRE, "
            "2018-2022: owned Prometheus and Alertmanager, migrated 80 services to Helm, cut "
            "deploy lead time from days to under an hour. Skills: Kubernetes, Go, Terraform, "
            "Argo CD, Crossplane, Prometheus, Grafana, AWS."
        ),
        resume_public=True,
    ),
    attendee(
        "Marisol Vantablack",
        "SRE on a 24/7 on-call rotation for a streaming company. Deep into OpenTelemetry, SLOs, "
        "and burn-rate alerting. Currently ripping out three vendor agents and replacing them "
        "with one Collector pipeline, and curious about eBPF-based profiling.",
        ["observability", "opentelemetry", "slos", "prometheus", "ebpf", "on-call"],
        blockout_times=[{"start_time": at("13:20"), "end_time": at("14:00")}],
    ),
    attendee(
        "Thaddeus Moonbeam-Okafor",
        "Security engineer focused on Kubernetes supply chain and runtime policy. I maintain "
        "our Kyverno policy library, sign everything with Sigstore, and am evaluating Cilium "
        "network policy to replace our IP-based rules. Happy to compare admission controller notes.",
        ["security", "supply chain", "sigstore", "kyverno", "cilium", "zero trust"],
        linkedin_url="https://www.linkedin.com/in/thaddeus-moonbeam-okafor-demo",
    ),
    attendee(
        "Juniper Hollowell-Zane",
        "ML platform engineer. I run GPU clusters for an applied research team: vLLM serving, "
        "Kubeflow training jobs, and a lot of arguing with the scheduler. Interested in RAG "
        "retrieval quality and how people are doing vector search at scale.",
        ["ai/ml on k8s", "gpu scheduling", "vllm", "kubeflow", "rag", "vector search"],
        resume_text=(
            "Juniper Hollowell-Zane. ML Platform Engineer, 2021-present: operate 120-GPU "
            "Kubernetes clusters; deployed vLLM and KServe inference with KEDA autoscaling; "
            "built Argo Workflows pipelines for embedding generation into Elasticsearch; "
            "reduced training job queue time 60 percent with Volcano gang scheduling. Earlier: "
            "data engineer on Spark and Airflow. Skills: Python, PyTorch, Kubernetes, CUDA, "
            "Kubeflow, Elasticsearch, Ray."
        ),
        resume_public=False,
    ),
    attendee(
        "Octavia Brightwater-Ng",
        "Search engineer. I own the Elasticsearch clusters behind a product catalog and am "
        "moving from pure BM25 to hybrid retrieval with semantic_text. Want to talk HNSW "
        "tuning, quantization, and memory sizing with anyone who has been burned by it.",
        ["search", "elasticsearch", "vector search", "hybrid search", "relevance", "hnsw"],
        linkedin_url="https://www.linkedin.com/in/octavia-brightwater-ng-demo",
    ),
    attendee(
        "Caspian Rookwood",
        "Kernel-adjacent backend developer learning eBPF. Shipped a small libbpf tool to trace "
        "slow syscalls in our ingest service and now want to understand Cilium and Parca "
        "internals. Also interested in networking debugging war stories.",
        ["ebpf", "linux", "networking", "cilium", "profiling", "performance"],
    ),
    attendee(
        "Wren Silvermoor-Adichie",
        "Engineering manager for a platform team of eight. Less hands-on these days; I care "
        "about measuring developer experience, multi-tenancy trade-offs, and how to justify "
        "platform investment to leadership. Looking to meet other platform leads.",
        ["platform engineering", "multi-tenancy", "developer experience", "leadership", "cost"],
        blockout_times=[
            {"start_time": at("11:40"), "end_time": at("12:20")},
            {"start_time": at("15:50"), "end_time": at("16:30")},
        ],
    ),
    attendee(
        "Lysander Peregrine-Mbatha",
        "DevOps engineer at a healthcare startup doing GitOps with Argo CD and Argo Rollouts. "
        "Working on progressive delivery with Prometheus-gated canaries and on getting secrets "
        "out of git with External Secrets Operator. Compliance makes everything twice as hard.",
        ["gitops", "argo rollouts", "progressive delivery", "secrets management", "compliance"],
        linkedin_url="https://www.linkedin.com/in/lysander-peregrine-mbatha-demo",
    ),
    attendee(
        "Seraphina Duskwalker",
        "Data scientist dipping into infrastructure. I build RAG applications and keep hitting "
        "retrieval quality walls; I want to understand chunking, reranking, and what the "
        "Kubernetes people mean when they say my pipeline is not production-ready.",
        ["rag", "llms", "embeddings", "search", "python"],
        discovery_opt_in=False,
    ),
    attendee(
        "Bartholomew Ashgrove-Tanaka",
        "Network engineer moving into cloud native. Spent a decade on BGP and firewalls, now "
        "debugging CoreDNS timeouts and conntrack exhaustion in Kubernetes. Interested in "
        "zero trust networking and in whether eBPF datapaths will finally make kube-proxy go away.",
        ["networking", "zero trust", "cilium", "dns", "ebpf", "kubernetes"],
        discovery_opt_in=False,
    ),
]


# --- HTTP -------------------------------------------------------------------------------------


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status


def post_json(
    base_url: str, path: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ApiError(exc.code, body) from None


def load_organizer_key() -> str:
    key = os.environ.get("ORGANIZER_API_KEY", "").strip()
    if key:
        return key
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("ORGANIZER_API_KEY="):
                value = line.split("=", 1)[1].strip().strip("'\"")
                if value and not value.startswith("<"):
                    return value
    sys.exit("ORGANIZER_API_KEY is not set (env or .env in the repo root).")


# --- Tokens file -----------------------------------------------------------------------------


def read_tokens(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data.get("attendees", {}) if isinstance(data, dict) else {}


def write_tokens(path: Path, attendees: dict[str, dict[str, str]]) -> None:
    body = {
        "conference_id": CONFERENCE_ID,
        "note": "Demo attendee bearer tokens. Gitignored. Send as 'Authorization: Bearer <token>'.",
        "attendees": attendees,
    }
    path.write_text(json.dumps(body, indent=2) + "\n")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


# --- Recommendations smoke check -------------------------------------------------------------


def flatten_people(attendees: Any) -> list[dict[str, Any]]:
    """Accept either a flat list or the {similar, matches} shape, de-duplicated by id."""
    if isinstance(attendees, list):
        candidates = attendees
    elif isinstance(attendees, dict):
        candidates = [*attendees.get("matches", []), *attendees.get("similar", [])]
    else:
        candidates = []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for person in candidates:
        pid = str(person.get("attendee_id", ""))
        if pid and pid not in seen:
            seen.add(pid)
            out.append(person)
    return out


def print_smoke_check(name: str, recommendations: dict[str, Any]) -> None:
    print(f"\nSmoke check for {name}:")
    talks = recommendations.get("talks", []) or []
    print("  Top talks:")
    for hit in talks[:3]:
        score = hit.get("score", hit.get("_score"))
        suffix = f" (score {score:.3f})" if isinstance(score, (int, float)) else ""
        print(f"    - {hit.get('title', '?')}{suffix}")
    if not talks:
        print("    (none)")
    people = flatten_people(recommendations.get("attendees"))
    print("  Top people:")
    for person in people[:3]:
        score = person.get("score")
        suffix = f" (score {score:.3f})" if isinstance(score, (int, float)) else ""
        why = person.get("why")
        print(f"    - {person.get('name', '?')}{suffix}")
        if why:
            print(f"        why: {str(why)[:160]}")
    if not people:
        print("    (none)")


# --- Main ------------------------------------------------------------------------------------


def dry_run() -> None:
    print(f"Conference: {CONFERENCE_NAME} ({CONFERENCE_ID}), {DAY} {TZ}")
    print(f"\nPOST /confirm-schedule  (header X-Organizer-Key)  talks={len(TALKS)}")
    rooms = sorted({t["room"] for t in TALKS})
    tracks = sorted({t["track"] for t in TALKS})
    print(f"  rooms={rooms}\n  tracks={tracks}")
    print("  sample talk:")
    print("  " + json.dumps(TALKS[1], indent=2).replace("\n", "\n  "))
    print(f"\nPOST /save-user-data  attendees={len(ATTENDEES)}")
    opt_in = sum(a["discovery_opt_in"] for a in ATTENDEES)
    with_resume = sum("resume_text" in a for a in ATTENDEES)
    with_blockouts = sum(bool(a["blockout_times"]) for a in ATTENDEES)
    print(f"  discovery_opt_in={opt_in}  resume_text={with_resume}  blockout_times={with_blockouts}")
    sample = dict(ATTENDEES[0])
    if "resume_text" in sample:
        sample["resume_text"] = sample["resume_text"][:60] + "..."
    print("  sample attendee:")
    print("  " + json.dumps(sample, indent=2).replace("\n", "\n  "))
    print("\nDry run: no requests sent.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API base URL (default {DEFAULT_BASE_URL})")
    parser.add_argument("--tokens-file", type=Path, default=DEFAULT_TOKENS_FILE, help="where attendee tokens are saved (gitignored, chmod 600)")
    parser.add_argument("--timeout", type=float, default=60.0, help="per-request timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="print payload shapes and exit without network access")
    args = parser.parse_args()

    if args.dry_run:
        dry_run()
        return 0

    organizer_key = load_organizer_key()
    base_url = args.base_url

    print(f"Seeding {CONFERENCE_NAME} ({CONFERENCE_ID}) -> {base_url}")
    try:
        schedule = post_json(
            base_url,
            "/confirm-schedule",
            {"conference_id": CONFERENCE_ID, "talks": TALKS},
            {"X-Organizer-Key": organizer_key},
            args.timeout,
        )
    except ApiError as exc:
        print(f"confirm-schedule failed: {exc}", file=sys.stderr)
        return 1
    print(f"Talks confirmed: {schedule.get('talk_count', len(TALKS))}  join_url={schedule.get('join_url', '?')}")

    tokens = read_tokens(args.tokens_file)
    first_recommendations: dict[str, Any] | None = None
    created = updated = 0
    for payload in ATTENDEES:
        name = payload["name"]
        existing = tokens.get(name)
        headers = {"Authorization": f"Bearer {existing['token']}"} if existing else {}
        try:
            try:
                result = post_json(base_url, "/save-user-data", payload, headers, args.timeout)
            except ApiError as exc:
                if existing and exc.status in (401, 403):
                    # Token no longer valid (indices swapped); create a fresh attendee.
                    existing = None
                    result = post_json(base_url, "/save-user-data", payload, {}, args.timeout)
                else:
                    raise
        except ApiError as exc:
            print(f"save-user-data failed for {name}: {exc}", file=sys.stderr)
            return 1
        attendee_id = result.get("attendee_id", "?")
        if existing:
            updated += 1
        else:
            created += 1
            token = result.get("attendee_token")
            if token:
                tokens[name] = {"attendee_id": attendee_id, "token": token}
        print(f"  {'updated' if existing else 'created'}  {attendee_id}  {name}")
        if first_recommendations is None:
            first_recommendations = result.get("recommendations", {})
            first_name = name

    write_tokens(args.tokens_file, tokens)
    print(f"\nAttendees: {created} created, {updated} updated. Tokens saved to {args.tokens_file} (mode 600).")
    if first_recommendations is not None:
        print_smoke_check(first_name, first_recommendations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
