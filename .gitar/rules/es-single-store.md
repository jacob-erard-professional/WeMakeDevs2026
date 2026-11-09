---
title: "Elasticsearch single store"
description: "Keep Elasticsearch as the only data, search and vector store for conference data"
when: "PRs that add a dependency, client, connection string, container, Kubernetes workload or migration for another database, cache or vector store, such as Postgres, MySQL, SQLite, MongoDB, Redis, Memcached, DynamoDB, Pinecone, Weaviate, Chroma, Qdrant, FAISS or SQLAlchemy / ORM models"
actions: "Request changes, point to the exact lines that introduce the store, and tell the author to put the data in an Elasticsearch index instead: a new index with mappings defined in code and created idempotently at startup, semantic_text or dense_vector for embeddings, and Elasticsearch caching or a short-lived in-process dict for caches. Pass if the store only appears in docs or in a test fixture that never ships"
type: check
---
