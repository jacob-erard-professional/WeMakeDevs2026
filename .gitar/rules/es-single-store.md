---
title: "Elasticsearch single store"
description: "Keep Elasticsearch as the only data, search and vector store for conference data"
when: "PRs that add a dependency, client, connection string, container, Kubernetes workload or migration for another database, cache or vector store, such as Postgres, MySQL, SQLite, MongoDB, Redis, Memcached, DynamoDB, Pinecone, Weaviate, Chroma, Qdrant, FAISS or SQLAlchemy / ORM models"
actions: "Request changes, point to the exact lines that introduce the store, and tell the author to put the data in an Elasticsearch index instead: a new index with mappings defined in code and created idempotently at startup, semantic_text or dense_vector for embeddings, and Elasticsearch caching or a short-lived in-process dict for caches. Pass if the store only appears in docs or in a test fixture that never ships"
type: check
---

# Elasticsearch single store

1. Fire when the diff adds a dependency (`pyproject.toml`, `uv.lock`, requirements), an import or client, a connection string, a Docker or Kubernetes workload, or a migration for a database, cache or vector store other than Elasticsearch: Postgres, MySQL, SQLite, MongoDB, Redis, Memcached, DynamoDB, Pinecone, Weaviate, Chroma, Qdrant, FAISS, SQLAlchemy or other ORM models.
2. Fail if the new store holds or caches conference data (talks, speakers, attendees, events, embeddings, search results) that Elasticsearch could hold.
3. Pass if the store appears only in documentation, in a test fixture that never ships, or is a short-lived in-process dict used as a cache.
4. On failure, request changes, point to the exact lines that introduce the store, and tell the author to use an Elasticsearch index instead: define mappings in code, create the index idempotently at startup, and use `semantic_text` or `dense_vector` for embeddings.
5. Do not auto-apply the replacement; it changes behaviour and needs the author to decide the mapping.
