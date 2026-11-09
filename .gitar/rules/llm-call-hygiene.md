---
title: "LLM call hygiene"
description: "Make sure every OpenAI / LLM call is bounded, configurable and traced"
when: "PRs that add or change application source code in any language (not tests or docs) calling OpenAI or any other LLM API: openai client calls, chat.completions / responses / embeddings, or an LLM SDK such as litellm, anthropic or langchain"
actions: "Check each call (1) sets a timeout on the client or the call and handles failure without crashing the request, (2) reads the model name from an environment variable or config value rather than a string literal, and (3) runs inside an OpenLIT or OpenTelemetry span. For each missing piece, request changes and comment on the exact file and line with the fix: the timeout argument to add, the env var to read (for example OPENAI_MODEL in .env.example), or where openlit.init() or the span should go. Pass when all three are present"
type: check
---
