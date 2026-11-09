"""Print Elasticsearch cluster health. Throwaway: tests the Gitar auto-apply/approve/merge flow."""
import json
import os
import urllib.request


def cluster_health():
    req = urllib.request.Request(
        os.environ.get("ES_URL", "http://localhost:9200") + "/_cluster/health",
        headers={"Authorization": "ApiKey " + os.environ["ES_API_KEY"]},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    print(cluster_health()["status"])
