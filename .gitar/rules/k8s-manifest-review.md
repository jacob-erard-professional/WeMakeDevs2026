---
title: "Kubernetes manifest check"
description: "Make sure Kubernetes changes will actually run on the demo cluster"
when: "PRs that add or modify files under k8s/ or any Kubernetes manifest"
actions: "Check every Deployment has resource requests/limits, readiness and liveness probes, and reads config from ConfigMaps or Secrets; comment with the exact missing fields and add the label k8s"
type: check
---
