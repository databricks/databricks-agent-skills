# GraphRAG Retrieval Patterns

GraphRAG retrieval should be explicit about the entrypoint, expansion strategy,
ranking, and provenance. Keep each retriever small and measurable; combine them
through a router rather than one large prompt.

## Pattern 1: AI Search Baseline

Start with AI Search hybrid retrieval. It combines semantic similarity with
keyword matching and is the default baseline for Databricks RAG.

```python
results = w.vector_search_indexes.query_index(
    index_name="catalog.schema.support_docs_index",
    columns=["doc_id", "chunk_id", "text", "product", "updated_at"],
    query_text=user_query,
    query_type="HYBRID",
    num_results=20,
    filters_json='{"status": "active"}',
)
```

Use this before GraphRAG. Add metadata filters for tenant, region, product,
classification, or document status. Add a reranker when the candidate set is
large enough and latency budget allows.

## Pattern 2: Vector-to-Graph Expansion

Use AI Search to find seed chunks or entities, then expand through graph
relationships for context.

1. Query AI Search for candidate chunks/entities.
2. Extract seed entity IDs from metadata or an entity-linking table.
3. Traverse bounded graph neighborhoods in Neo4j or another graph store.
4. Return passages plus graph facts with provenance.

```cypher
MATCH (seed:Entity {entity_id: $entity_id})-[r:RELATED_TO*1..2]-(neighbor:Entity)
RETURN seed.name, type(r[0]) AS relationship, neighbor.name, neighbor.source_doc_id
LIMIT 50
```

Use when semantically similar text points to the right area, but the answer needs
relationships such as "owned by", "depends on", "contraindicated with", or
"part of".

## Pattern 3: Full-Text + Graph Traversal

Use a full-text graph index when exact entity names, SKUs, contract IDs, or
technical identifiers drive recall. Then expand from matched nodes.

```cypher
CALL db.index.fulltext.queryNodes('entityText', $query, {limit: 20})
YIELD node, score
MATCH (node)-[r:MENTIONS|CAUSES|OWNS*1..2]-(related)
RETURN node.name, score, collect(DISTINCT related.name)[0..20] AS related_entities
```

This is often better than pure vector search for canonical entity names and
controlled vocabularies.

## Pattern 4: Text2Cypher

Text2Cypher turns a user question into a read-only Cypher query. Use it only when
the graph schema is curated and the question asks for graph facts or paths.

Safety requirements:

- Provide the model a compact schema: labels, relationship types, allowed
  properties, examples, and forbidden operations.
- Reject or rewrite generated Cypher containing `CREATE`, `MERGE`, `DELETE`,
  `SET`, `CALL dbms`, file access, or unbounded path expansion.
- Add `LIMIT` and timeout controls.
- Return the generated Cypher in traces for review.

## Pattern 5: Router / Supervisor

Use a router when query types differ:

| Query type | Retriever |
|---|---|
| Semantic document lookup | AI Search hybrid |
| Exact entity relationship | Full-text + graph traversal |
| Path/multi-hop graph question | Text2Cypher or bounded traversal |
| SQL aggregate over governed tables | Genie or SQL tool |
| Managed document Q&A baseline | Knowledge Assistant |

Databricks Apps can host the router and tool calls. Model Serving can host an
agent endpoint when the application needs a served API. MLflow traces should tag
the chosen retriever, candidate count, latency, token count, and final answer
groundedness.
