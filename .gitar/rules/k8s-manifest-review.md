---
title: "Kubernetes manifest check"
description: "Make sure Kubernetes changes will actually run on the demo cluster"
when: "PRs that add or modify files under k8s/ or any Kubernetes manifest"
actions: "Check every Deployment has resource requests/limits, readiness and liveness probes, and reads config from ConfigMaps or Secrets; comment with the exact missing fields and add the label k8s"
type: check
---

# Kubernetes manifest check

1. Fire on any added or changed file under `k8s/` or any YAML containing a Kubernetes `kind:` such as Deployment, StatefulSet, Service, HorizontalPodAutoscaler or Rollout. Docs and non-manifest files are out of scope.
2. For each Deployment, StatefulSet or Rollout, fail if any container lacks `resources.requests` and `resources.limits` for both cpu and memory.
3. Fail if a container has no `readinessProbe` or no `livenessProbe`.
4. Fail if a container hardcodes configuration or credentials in `env` values instead of `configMapKeyRef` / `secretKeyRef` or `envFrom`.
5. Fail if the change removes probes, limits or replicas that already existed, or changes the web app's NodePort away from 30080 without explanation in the PR.
6. On failure, comment on the exact manifest and container with the missing fields, add the label `k8s`, and request changes. Pass when every workload in the diff has all of the above.
