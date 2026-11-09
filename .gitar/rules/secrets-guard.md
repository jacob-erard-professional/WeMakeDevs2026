---
title: "Secrets guard"
description: "Block credentials from being committed during the hackathon"
when: "PRs that add API keys, tokens, passwords, .env files or Elasticsearch / Dash0 / OpenAI credentials to the repository"
actions: "Request changes, point to the exact lines, and tell the author to move the value into .env (which is gitignored) and document the variable name in .env.example"
type: check
---

# Secrets guard

1. Scan every added or changed line in the diff for credential values: API keys, bearer tokens, passwords, Elasticsearch `ES_API_KEY` values, Dash0 `OTEL_EXPORTER_OTLP_HEADERS` tokens, OpenAI `sk-...` keys, private keys and connection strings with embedded passwords.
2. Fail if a `.env` file (or any file that looks like one) is added or modified in the repo, regardless of its contents.
3. Pass for `.env.example` as long as every value is a `<PLACEHOLDER>` style token, not a real value.
4. Pass for variable names, `os.environ[...]` reads, Kubernetes `secretKeyRef` references and documentation that mentions a variable without its value.
5. On failure, request changes, comment on each offending file and line, and tell the author to move the value into `.env` and add the variable name with a placeholder to `.env.example`. Remind them to rotate any value that was pushed.
