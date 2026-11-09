---
title: "OpenTelemetry instrumentation check"
description: "Make sure every new code path shows up in Dash0 traces"
when: "PRs that add or change application source code in any language (not tests, docs, manifests or config) introducing a new HTTP route handler, an Elasticsearch query or index call, an OpenAI / LLM call, or a background job, scheduled task or queue consumer"
actions: "For each new code path, check it runs inside an OpenTelemetry span (its own tracer.start_as_current_span, an auto-instrumented framework or client, or OpenLIT for LLM calls) or records a metric. If none, request changes and comment on the exact file and line where the span should open, which operation it should wrap and which attributes to set (for example talk.id, search.query, gen_ai.request.model). Pass when every new path is covered"
type: check
---
