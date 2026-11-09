---
title: "LLM call hygiene"
description: "Make sure every OpenAI / LLM call is bounded, configurable and traced"
when: "PRs that add or change application source code in any language (not tests or docs) calling OpenAI or any other LLM API: openai client calls, chat.completions / responses / embeddings, or an LLM SDK such as litellm, anthropic or langchain"
actions: "Check each call (1) sets a timeout on the client or the call and handles failure without crashing the request, (2) reads the model name from an environment variable or config value rather than a string literal, and (3) runs inside an OpenLIT or OpenTelemetry span. For each missing piece, request changes and comment on the exact file and line with the fix: the timeout argument to add, the env var to read (for example OPENAI_MODEL in .env.example), or where openlit.init() or the span should go. Pass when all three are present"
type: check
---

# LLM call hygiene

1. Fire only on added or changed application source (any language, including the TypeScript frontend) that calls an LLM: the `openai` client (`chat.completions`, `responses`, `embeddings`), or an SDK such as `litellm`, `anthropic` or `langchain`. Skip test-only and docs-only PRs.
2. Timeout: pass if the client is constructed with `timeout=` or the call passes a timeout, and the failure path returns a clear error instead of an unhandled exception. Fail otherwise.
3. Model name: pass if the model comes from an environment variable or config value (for example `OPENAI_MODEL`, documented in `.env.example`). Fail if it is a string literal at the call site.
4. Tracing: pass if the call runs inside an OpenLIT-instrumented client (`openlit.init()` at startup) or an explicit OpenTelemetry span. Fail otherwise.
5. Also fail if the API key is read from anywhere other than an environment variable; the secrets guard rule covers committed values.
6. On any failure, request changes and comment on the exact file and line with the concrete fix: the timeout argument, the env var to read, or where `openlit.init()` or the span should go. Pass when all three checks pass.
