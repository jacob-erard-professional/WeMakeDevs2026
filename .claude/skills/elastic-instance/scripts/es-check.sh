#!/usr/bin/env bash
# Read-only health check of the team's Elastic Cloud Serverless project.
# Reads ES_URL / ES_API_KEY from the repo .env one key at a time (never `source`,
# never echoes a value) and runs the operator recipes from SKILL.md:
#   GET /, _cat/indices, _cat/aliases, _mapping of the app indices, _count,
#   one semantic query on talks-archive, _inference/_all, Agent Builder agents.
# Nothing here writes to the cluster.
#
#   .claude/skills/elastic-instance/scripts/es-check.sh            # .env at repo root
#   .claude/skills/elastic-instance/scripts/es-check.sh /path/.env  # another .env
set -euo pipefail

env_file="${1:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.env}"
[[ -f "$env_file" ]] || { echo "No .env at $env_file" >&2; exit 1; }

env_value() { { grep -m1 "^$1=" "$env_file" || true; } | cut -d= -f2- | tr -d '"'"'"; }
ES_URL="$(env_value ES_URL)"
ES_API_KEY="$(env_value ES_API_KEY)"
[[ -n "$ES_URL" && -n "$ES_API_KEY" ]] || { echo "ES_URL or ES_API_KEY missing in $env_file" >&2; exit 1; }
KB_URL="${ES_URL/.es./.kb.}"; KB_URL="${KB_URL%:443}"

out="$(mktemp)"; trap 'rm -f "$out"' EXIT
# Prints only the HTTP status; the body lands in $out for the summaries below.
es() { curl -s -m 30 -o "$out" -w '%{http_code}' -H "Authorization: ApiKey $ES_API_KEY" \
         -H 'Content-Type: application/json' -H 'kbn-xsrf: true' "$@" || echo 000; }
py() { python3 -I -c "$1" "$out" || python3 -I -c 'import json,sys
try:
    e=json.load(open(sys.argv[1])).get("error",{})
    if isinstance(e,dict) and "type" in e and "reason" in e:
        print("  error",e["type"],e["reason"])
    else:
        print("  unparseable response")
except Exception:
    print("  unparseable response")' "$out" || true; }

echo "Elasticsearch: ${ES_URL#https://}"
echo "Kibana:        ${KB_URL#https://}"

echo; echo "[GET /]  HTTP $(es "$ES_URL/")"
py 'import json,sys;d=json.load(open(sys.argv[1]));print("  version",d["version"]["number"],d["version"]["build_flavor"])'

echo; echo "[_cat/indices]  HTTP $(es "$ES_URL/_cat/indices?v&h=index,docs.count,store.size&s=index")"
sed 's/^/  /' "$out"

echo; echo "[_cat/aliases]  HTTP $(es "$ES_URL/_cat/aliases?v&h=alias,index,is_write_index")"
sed 's/^/  /' "$out"

echo; echo "[_mapping talks,attendees,connections]  HTTP $(es "$ES_URL/talks,attendees,connections/_mapping")"
py 'import json,sys
d=json.load(open(sys.argv[1]))
for idx,m in sorted(d.items()):
    mp=m["mappings"]; props=mp.get("properties",{})
    sem=[f"{f}->{p.get('"'"'inference_id'"'"')}" for f,p in props.items() if p.get("type")=="semantic_text"]
    print(f"  {idx}: dynamic={mp.get('"'"'dynamic'"'"')} fields={len(props)} semantic_text={sem or None}")'

echo; echo "[_count]"
for idx in talks attendees connections talks-archive; do
  code="$(es "$ES_URL/$idx/_count")"
  printf '  %-14s HTTP %s  count=%s\n' "$idx" "$code" \
    "$(py 'import json,sys;print(json.load(open(sys.argv[1])).get("count","?"))')"
done

echo; echo "[semantic search talks-archive]  HTTP $(es -X POST "$ES_URL/talks-archive/_search" -d '{
  "size": 3, "_source": ["title", "conference", "year"],
  "query": {"semantic": {"field": "semantic_content", "query": "something on eBPF and security"}}}')"
py 'import json,sys;d=json.load(open(sys.argv[1]));print("  took_ms",d["took"])
for h in d["hits"]["hits"]:
    s=h["_source"];print("  %.3f  %s  (%s %s)"%(h["_score"],s.get("title"),s.get("conference"),s.get("year")))'

echo; echo "[_inference/_all]  HTTP $(es "$ES_URL/_inference/_all")"
py 'import json,sys;d=json.load(open(sys.argv[1]))
for e in sorted(d["endpoints"],key=lambda e:(e["task_type"],e["inference_id"])):
    print("  %-16s %-44s service=%s"%(e["task_type"],e["inference_id"],e.get("service")))'

echo; echo "[Kibana agent_builder agents]  HTTP $(es "$KB_URL/api/agent_builder/agents")"
py 'import json,sys;d=json.load(open(sys.argv[1]));r=d.get("results",d) if isinstance(d,dict) else d
for a in (r if isinstance(r,list) else []): print("  ",a.get("id"),"|",a.get("name"))'
