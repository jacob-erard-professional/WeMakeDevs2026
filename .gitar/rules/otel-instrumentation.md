---
title: "OpenTelemetry instrumentation check"
description: "Make sure every new code path shows up in Dash0 traces"
when: "PRs that add or change application source code in any language (not tests, docs, manifests or config) introducing a new HTTP route handler, an Elasticsearch query or index call, an OpenAI / LLM call, or a background job, scheduled task or queue consumer"
actions: "For each new code path, check it runs inside an OpenTelemetry span (its own tracer.start_as_current_span, an auto-instrumented framework or client, or OpenLIT for LLM calls) or records a metric. If none, request changes and comment on the exact file and line where the span should open, which operation it should wrap and which attributes to set (for example talk.id, search.query, gen_ai.request.model). Pass when every new path is covered"
type: check
---

# OpenTelemetry instrumentation check

1. Fire only on added or changed application source (any language, including the TypeScript frontend). Skip PRs that touch only tests, docs, `k8s/` manifests, CI or config.
2. Identify each new code path: an HTTP route handler, a call to the Elasticsearch client (search, index, bulk, get), an OpenAI or other LLM call, or a background job, scheduled task or queue consumer.
3. A path passes if it runs inside a span: an explicit `tracer.start_as_current_span(...)`, a framework or client that is auto-instrumented by `opentelemetry-instrument`, or OpenLIT for LLM calls. Recording a metric for the operation also counts.
4. Fail if a new path has none of those, or if the PR introduces a hand-rolled tracing or metrics client instead of OpenTelemetry.
5. Prefer that spans carry domain attributes such as `talk.id`, `search.query`, `search.results` and `gen_ai.request.model`; missing attributes are a comment, not a failure.
6. On failure, request changes and comment on the exact file and line where the span should open, what it should wrap and which attributes to set. Pass when every new path is covered.
