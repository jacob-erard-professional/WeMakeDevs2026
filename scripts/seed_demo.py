#!/usr/bin/env python3
"""Seed one live demo conference through the public HTTP API.

Flow: POST /conferences (no auth) creates the conference and returns an organizer token;
POST /confirm-schedule (header X-Organizer-Token) stores 20 talks; POST /save-user-data
(multipart, `profile` JSON field) creates 10 fake attendees. Elasticsearch is never touched
directly. Stdlib only; Python 3.11+.

    python3 scripts/seed_demo.py                      # against prod
    python3 scripts/seed_demo.py --base-url http://localhost:8000
    python3 scripts/seed_demo.py --dry-run            # print payload shapes, no network
    python3 scripts/seed_demo.py --new-conference     # ignore the saved conference, make another

The organizer token and attendee bearer tokens are written to the gitignored, mode-600 file
scripts/.seed-organizer.json and are never printed. Re-running reuses the saved conference:
talks carry stable `talk_id`s so confirm-schedule overwrites them, and attendees whose token
is saved are updated in place instead of duplicated. Only the conference_id, join URL and
counts are printed.
"""

from __future__ import annotations

import argparse
import json
import stat
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BASE_URL = "https://wearedevs.cnh.radarhq.io/api"
PUBLIC_SITE = "https://wearedevs.cnh.radarhq.io"
DEFAULT_STATE_FILE = SCRIPT_DIR / ".seed-organizer.json"

CONFERENCE_NAME = "Cloud Native Hackathon SLC 2026"
TALK_ID_PREFIX = "cnh-slc-2026"
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
        "talk_id": f"{TALK_ID_PREFIX}-t{num:02d}",
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
    looking_for: str,
    interests: list[str],
    *,
    linkedin_url: str | None = None,
    discovery_opt_in: bool = True,
    blockout_times: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    handle = name.lower().replace(" ", ".")
    payload: dict[str, Any] = {
        "name": name,
        "email": f"{handle}@example.com",
        "bio": bio,
        "looking_for": looking_for,
        "interests": interests,
        "blockout_times": blockout_times or [],
        "discovery_opt_in": discovery_opt_in,
    }
    if linkedin_url:
        payload["linkedin_url"] = linkedin_url
    return payload


# Clearly fake names; example.com emails; no real people. No resumes.
ATTENDEES: list[dict[str, Any]] = [
    attendee(
        "Zephyr Quillfeather",
        "Platform engineer at a mid-size fintech. I run our internal developer platform on "
        "Kubernetes with Argo CD and Crossplane and spend most of my time making golden paths "
        "developers actually follow. Trying to figure out whether Backstage is worth the upkeep.",
        "Other platform teams who have run Backstage in production for more than a year and can "
        "tell me honestly whether the scaffolder and catalog paid for themselves.",
        ["platform engineering", "gitops", "argo cd", "crossplane", "backstage", "developer experience"],
        linkedin_url="https://www.linkedin.com/in/zephyr-quillfeather-demo",
    ),
    attendee(
        "Marisol Vantablack",
        "SRE on a 24/7 on-call rotation for a streaming company. Deep into OpenTelemetry, SLOs, "
        "and burn-rate alerting. Currently ripping out three vendor agents and replacing them "
        "with one Collector pipeline, and curious about eBPF-based profiling.",
        "People running a single OpenTelemetry Collector pipeline at scale, and anyone using "
        "continuous profiling to cut on-call toil.",
        ["observability", "opentelemetry", "slos", "prometheus", "ebpf", "on-call"],
        blockout_times=[{"start_time": at("13:20"), "end_time": at("14:00")}],
    ),
    attendee(
        "Thaddeus Moonbeam-Okafor",
        "Security engineer focused on Kubernetes supply chain and runtime policy. I maintain "
        "our Kyverno policy library, sign everything with Sigstore, and am evaluating Cilium "
        "network policy to replace our IP-based rules. Happy to compare admission controller notes.",
        "Teams that have migrated from Calico to Cilium identity-based policy, and anyone "
        "enforcing Sigstore provenance at admission in production.",
        ["security", "supply chain", "sigstore", "kyverno", "cilium", "zero trust"],
        linkedin_url="https://www.linkedin.com/in/thaddeus-moonbeam-okafor-demo",
    ),
    attendee(
        "Juniper Hollowell-Zane",
        "ML platform engineer. I run GPU clusters for an applied research team: vLLM serving, "
        "Kubeflow training jobs, and a lot of arguing with the scheduler. Interested in RAG "
        "retrieval quality and how people are doing vector search at scale.",
        "Search engineers who can help me measure and improve retrieval quality for RAG, and "
        "anyone autoscaling LLM inference on queue depth.",
        ["ai/ml on k8s", "gpu scheduling", "vllm", "kubeflow", "rag", "vector search"],
    ),
    attendee(
        "Octavia Brightwater-Ng",
        "Search engineer. I own the Elasticsearch clusters behind a product catalog and am "
        "moving from pure BM25 to hybrid retrieval with semantic_text. Want to talk HNSW "
        "tuning, quantization, and memory sizing with anyone who has been burned by it.",
        "ML platform folks building RAG pipelines on top of Elasticsearch, and operators who "
        "have sized kNN workloads on Kubernetes.",
        ["search", "elasticsearch", "vector search", "hybrid search", "relevance", "hnsw"],
        linkedin_url="https://www.linkedin.com/in/octavia-brightwater-ng-demo",
    ),
    attendee(
        "Caspian Rookwood",
        "Kernel-adjacent backend developer learning eBPF. Shipped a small libbpf tool to trace "
        "slow syscalls in our ingest service and now want to understand Cilium and Parca "
        "internals. Also interested in networking debugging war stories.",
        "eBPF practitioners willing to review a small libbpf tool and point me at the sharp "
        "edges of CO-RE, plus network engineers with Kubernetes DNS debugging stories.",
        ["ebpf", "linux", "networking", "cilium", "profiling", "performance"],
    ),
    attendee(
        "Wren Silvermoor-Adichie",
        "Engineering manager for a platform team of eight. Less hands-on these days; I care "
        "about measuring developer experience, multi-tenancy trade-offs, and how to justify "
        "platform investment to leadership. Looking to meet other platform leads.",
        "Other platform engineering leads who have made the multi-tenancy call between "
        "namespaces, vCluster and separate clusters, and can share the cost numbers.",
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
        "Anyone running Argo Rollouts analysis against Prometheus or OpenTelemetry metrics, and "
        "security people who have audited secrets management in a regulated environment.",
        ["gitops", "argo rollouts", "progressive delivery", "secrets management", "compliance"],
        linkedin_url="https://www.linkedin.com/in/lysander-peregrine-mbatha-demo",
    ),
    attendee(
        "Seraphina Duskwalker",
        "Data scientist dipping into infrastructure. I build RAG applications and keep hitting "
        "retrieval quality walls; I want to understand chunking, reranking, and what the "
        "Kubernetes people mean when they say my pipeline is not production-ready.",
        "Patient infrastructure engineers who can explain what production-ready means for an "
        "embedding pipeline, and search people who have tuned chunking and reranking.",
        ["rag", "llms", "embeddings", "search", "python"],
        discovery_opt_in=False,
    ),
    attendee(
        "Bartholomew Ashgrove-Tanaka",
        "Network engineer moving into cloud native. Spent a decade on BGP and firewalls, now "
        "debugging CoreDNS timeouts and conntrack exhaustion in Kubernetes. Interested in "
        "zero trust networking and in whether eBPF datapaths will finally make kube-proxy go away.",
        "Cilium users who replaced kube-proxy with the eBPF datapath, and anyone with a "
        "repeatable method for chasing intermittent DNS failures in clusters.",
        ["networking", "zero trust", "cilium", "dns", "ebpf", "kubernetes"],
        discovery_opt_in=False,
    ),
]


# --- HTTP -------------------------------------------------------------------------------------


class ApiError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:500]}")
        self.status = status


def _request(
    base_url: str, path: str, body: bytes, headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        method="POST",
        headers={"Accept": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raise ApiError(exc.code, exc.read().decode("utf-8", errors="replace")) from None


def post_json(
    base_url: str, path: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    return _request(base_url, path, body, {"Content-Type": "application/json", **headers}, timeout)


def post_profile_multipart(
    base_url: str, profile: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    """/save-user-data as multipart/form-data with a JSON `profile` field and no resume."""
    boundary = f"----seed{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="profile"\r\n'
        "Content-Type: application/json\r\n\r\n"
        f"{json.dumps(profile)}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    content_type = f"multipart/form-data; boundary={boundary}"
    return _request(
        base_url, "/save-user-data", body, {"Content-Type": content_type, **headers}, timeout
    )


def get_json(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raise ApiError(exc.code, exc.read().decode("utf-8", errors="replace")) from None


# --- State file (organizer token + attendee tokens; never printed) ---------------------------


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_state(path: Path, state: dict[str, Any]) -> None:
    state["note"] = (
        "Seeded demo conference secrets. Gitignored. organizer_token goes in header "
        "X-Organizer-Token; attendee tokens go in 'Authorization: Bearer <token>'."
    )
    path.write_text(json.dumps(state, indent=2) + "\n")
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
        print(f"    - {hit.get('title', '?')}")
    if not talks:
        print("    (none)")
    people = flatten_people(recommendations.get("attendees"))
    print("  Top people:")
    for person in people[:3]:
        print(f"    - {person.get('name', '?')}")
        if person.get("why"):
            print(f"        why: {str(person['why'])[:160]}")
    if not people:
        print("    (none)")


# --- Main ------------------------------------------------------------------------------------


def dry_run() -> None:
    print(f"Conference: {CONFERENCE_NAME}, {DAY} {TZ}")
    print("\nPOST /conferences  (no auth)  body={'name': ...} -> conference_id + organizer_token")
    print(f"\nPOST /confirm-schedule  (header X-Organizer-Token)  talks={len(TALKS)}")
    print(f"  rooms={sorted({t['room'] for t in TALKS})}")
    print(f"  tracks={sorted({t['track'] for t in TALKS})}")
    print("  sample talk:")
    print("  " + json.dumps(TALKS[1], indent=2).replace("\n", "\n  "))
    print(f"\nPOST /save-user-data  (multipart, field 'profile')  attendees={len(ATTENDEES)}")
    opt_in = sum(a["discovery_opt_in"] for a in ATTENDEES)
    with_blockouts = sum(bool(a["blockout_times"]) for a in ATTENDEES)
    print(f"  discovery_opt_in={opt_in}  blockout_times={with_blockouts}  resumes=0")
    print("  sample profile (conference_id filled at runtime):")
    print("  " + json.dumps(ATTENDEES[0], indent=2).replace("\n", "\n  "))
    print("\nGET /join/<conference_id>  (public) -> confirmed talks")
    print("\nDry run: no requests sent.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API base URL (default {DEFAULT_BASE_URL})")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE, help="where the organizer and attendee tokens are saved (gitignored, chmod 600)")
    parser.add_argument("--new-conference", action="store_true", help="ignore any saved conference and create a new one")
    parser.add_argument("--timeout", type=float, default=60.0, help="per-request timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="print payload shapes and exit without network access")
    args = parser.parse_args()

    if args.dry_run:
        dry_run()
        return 0

    base_url = args.base_url
    state = {} if args.new_conference else read_state(args.state_file)
    conference_id = state.get("conference_id")
    organizer_token = state.get("organizer_token")

    if not (conference_id and organizer_token):
        try:
            created = post_json(base_url, "/conferences", {"name": CONFERENCE_NAME}, {}, args.timeout)
        except ApiError as exc:
            print(f"POST /conferences failed: {exc}", file=sys.stderr)
            return 1
        conference_id = created["conference_id"]
        organizer_token = created["organizer_token"]
        state = {"conference_id": conference_id, "organizer_token": organizer_token, "attendees": {}}
        write_state(args.state_file, state)
        print(f"Created conference {conference_id} ({CONFERENCE_NAME})")
    else:
        print(f"Reusing conference {conference_id} from {args.state_file}")

    try:
        schedule = post_json(
            base_url,
            "/confirm-schedule",
            {"conference_id": conference_id, "talks": TALKS},
            {"X-Organizer-Token": organizer_token},
            args.timeout,
        )
    except ApiError as exc:
        print(f"confirm-schedule failed: {exc}", file=sys.stderr)
        if exc.status in (401, 403):
            print("Saved organizer token was rejected; re-run with --new-conference.", file=sys.stderr)
        return 1
    print(f"Talks confirmed: {schedule.get('talk_count', len(TALKS))}")

    attendee_tokens: dict[str, dict[str, str]] = state.setdefault("attendees", {})
    first_recommendations: dict[str, Any] | None = None
    first_name = ""
    created_n = updated_n = 0
    for base_profile in ATTENDEES:
        name = base_profile["name"]
        profile = {"conference_id": conference_id, **base_profile}
        existing = attendee_tokens.get(name)
        headers = {"Authorization": f"Bearer {existing['token']}"} if existing else {}
        try:
            try:
                result = post_profile_multipart(base_url, profile, headers, args.timeout)
            except ApiError as exc:
                if existing and exc.status in (401, 403):
                    existing = None
                    result = post_profile_multipart(base_url, profile, {}, args.timeout)
                else:
                    raise
        except ApiError as exc:
            print(f"save-user-data failed for {name}: {exc}", file=sys.stderr)
            write_state(args.state_file, state)
            return 1
        attendee_id = result.get("attendee_id", "?")
        if existing:
            updated_n += 1
        else:
            created_n += 1
            if result.get("attendee_token"):
                attendee_tokens[name] = {"attendee_id": attendee_id, "token": result["attendee_token"]}
        print(f"  {'updated' if existing else 'created'}  {attendee_id}  {name}")
        if first_recommendations is None:
            first_recommendations = result.get("recommendations", {})
            first_name = name
    write_state(args.state_file, state)

    try:
        joined = get_json(base_url, f"/join/{conference_id}", args.timeout)
        join_talks = len(joined.get("talks", []))
    except ApiError as exc:
        print(f"GET /join/{conference_id} failed: {exc}", file=sys.stderr)
        join_talks = -1

    print(f"\nConference: {conference_id}")
    print(f"Join URL:   {PUBLIC_SITE}/join/{conference_id}")
    print(f"Talks on join page: {join_talks}")
    print(f"Attendees: {created_n} created, {updated_n} updated")
    print(f"Tokens saved to {args.state_file} (mode 600, gitignored)")
    if first_recommendations is not None:
        print_smoke_check(first_name, first_recommendations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
