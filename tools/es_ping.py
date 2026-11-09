"""Print Elasticsearch cluster health. Throwaway: tests the Gitar auto-apply/approve/merge flow."""
import json
import os
import urllib.error
import urllib.request

from opentelemetry import trace

tracer = trace.get_tracer(__name__)


def cluster_health(timeout=10):
    req = urllib.request.Request(
        os.environ.get("ES_URL", "http://localhost:9200") + "/_cluster/health",
        headers={"Authorization": "ApiKey " + os.environ["ES_API_KEY"]},
    )
    with tracer.start_as_current_span("es.cluster_health"):
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())


if __name__ == "__main__":
    try:
        print(cluster_health()["status"])
    except (KeyError, urllib.error.URLError, TimeoutError):
        raise SystemExit("Elasticsearch health check failed")
