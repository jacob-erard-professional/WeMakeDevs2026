---
title: "Secrets guard"
description: "Block credentials from being committed during the hackathon"
when: "PRs that add API keys, tokens, passwords, .env files or Elasticsearch / Dash0 / OpenAI credentials to the repository"
actions: "Request changes, point to the exact lines, and tell the author to move the value into .env (which is gitignored) and document the variable name in .env.example"
type: check
---
