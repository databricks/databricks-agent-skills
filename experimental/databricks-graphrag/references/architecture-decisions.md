# GraphRAG Architecture Decisions

Use GraphRAG when explicit relationships are part of the answer, not because it
sounds more advanced than RAG. The safest Databricks path is to start with a
measured AI Search baseline, then add graph retrieval only when evaluation shows
relationship context improves quality enough to justify the extra operational
cost.

## Decision Tree

1. **Can AI Search answer it with hybrid retrieval?**
   - Use AI Search hybrid when questions need both semantic recall and exact
     identifiers such as SKUs, policy IDs, entity names, error codes, or product
     names.
   - Add metadata filters and a reranker before introducing graph traversal.
2. **Does the user need relationship paths?**
   - Use GraphRAG when answers depend on graph facts: ownership chains,
     dependency paths, customer-product-symptom links, policy exceptions, or
     multi-hop relationships.
3. **Is the graph schema stable enough?**
   - GraphRAG works best with curated labels, relationship types, primary keys,
     and provenance columns. If the schema changes every week, keep the graph as
     a derived index built from governed Unity Catalog tables.
4. **Can the question be routed safely?**
   - Use a router that chooses among AI Search, graph traversal, Text2Cypher,
     SQL/Genie, or a managed Knowledge Assistant.

## Architecture Options

| Pattern | Use when | Databricks spine | Graph component |
|---|---|---|---|
| Databricks-native RAG | Documents and metadata are enough | Unity Catalog -> AI Search -> Databricks Apps or Model Serving -> MLflow | None |
| Vector-to-graph expansion | Similar chunks identify seed entities, then relationships add context | AI Search for seeds; UC for source/provenance; MLflow for eval | Neo4j or graph DB traversal |
| Full-text + graph traversal | Entity names and exact identifiers dominate | UC source tables; App/API orchestration | Full-text index plus graph relationships |
| Text2Cypher | Users ask graph-schema questions directly | Databricks App or serving endpoint with prompt safety | Read-only Cypher generation |
| Router / supervisor | Different question types need different retrievers | Databricks Apps or Agent Bricks supervisor; MLflow traces | Optional retriever tools |

## Databricks Integration Spine

- **Unity Catalog** governs source Delta tables, entity and relationship tables,
  AI Search indexes, registered models, permissions, lineage, and auditability.
- **AI Search** is the default retrieval baseline. Use hybrid search, filters,
  and reranking before graph traversal.
- **Databricks Apps** are the preferred place to host custom GraphRAG UX, query
  routers, and API endpoints because app resources avoid hardcoded credentials.
- **Model Serving** is appropriate when serving custom models, embeddings,
  rerankers, or an agent endpoint outside an App.
- **MLflow** records traces, retrieval spans, scorer output, and versioned
  comparisons across ANN, hybrid, reranker, graph traversal, and Text2Cypher.

## Anti-Patterns

- Building a graph before defining answer shapes and evaluation metrics.
- Using Text2Cypher on an unconstrained schema or allowing write/delete Cypher.
- Treating Neo4j or a LangChain GraphRAG demo as a Databricks-native API.
- Skipping the AI Search baseline; most retrieval quality issues are fixed with
  parsing, chunking, metadata filters, hybrid search, or a reranker.
- Returning graph facts without source documents, entity IDs, or provenance.
