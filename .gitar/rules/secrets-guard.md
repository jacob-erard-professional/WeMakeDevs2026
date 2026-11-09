---
title: "Secrets guard"
description: "Block credentials from being committed during the hackathon"
when: "PRs that add API keys, tokens, passwords, .env files or Elasticsearch / Dash0 / OpenAI credentials to the repository"
actions: "Request changes, point to the exact lines, and tell the author to move the value into .env (which is gitignored) and document the variable name in .env.example"
type: check
---

# Secrets guard

1. Scan every added or changed line in the diff for values that look like real credentials: OpenAI `sk-...` keys, Elasticsearch API keys (base64 blobs or `ApiKey <value>` headers), Dash0 `auth_...` tokens, `Bearer <value>` headers where the value is not a placeholder, passwords, private key blocks, connection strings with an embedded password, and any long high-entropy string assigned to a variable or header named key, token, secret, password or authorization.
2. Fail if a `.env` file (or any other dotenv-style file that is not `.env.example`) is added or modified in the repo, regardless of its contents.
3. `.env.example` passes when each sensitive variable (`OPENAI_API_KEY`, `ES_API_KEY`, `OTEL_EXPORTER_OTLP_ENDPOINT`, the token inside `OTEL_EXPORTER_OTLP_HEADERS`) is empty or a `<PLACEHOLDER>` token, even inside a scheme such as `Bearer <DASH0_AUTH_TOKEN>`. Non-credential config (`ES_URL`, `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_*_EXPORTER`, `OPENAI_MODEL`) may carry real values. Fail only on a line whose value matches step 1.
4. Pass for variable names, `os.environ[...]` reads, Kubernetes `secretKeyRef` / `envFrom` references, hostnames and URLs without embedded credentials, and documentation that mentions a variable without its value.
5. On failure, request changes, comment on each offending file and line, and tell the author to move the value into `.env` and leave the variable in `.env.example` empty or as a `<PLACEHOLDER>`. Remind them to rotate any value that was pushed.
