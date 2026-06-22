# GraphRAG Evaluation and Operations

Do not recommend GraphRAG unless it beats a simpler AI Search baseline on
measured quality, latency, cost, or explainability. GraphRAG adds pipelines,
schemas, indexes, graph-store operations, and prompt-safety risk.

## Evaluation Protocol

1. **Create an evaluation set** with representative questions, expected answer
   notes, expected entities/relationships, and source documents.
2. **Run retrieval variants**: ANN, AI Search hybrid, hybrid + reranker, graph
   traversal, Text2Cypher, and router combinations.
3. **Score retrieval** with Recall@k, Precision@k, MRR, DCG@10, entity/path
   recall, and latency p95.
4. **Score answer quality** with MLflow judges for groundedness, context
   relevance, context sufficiency, safety, and task-specific correctness.
5. **Inspect traces** for missed entities, bad graph paths, hallucinated Cypher,
   stale edges, and over-broad graph expansion.

## MLflow Trace Tags

Record enough metadata to debug retrieval choices:

```python
with mlflow.start_span(name="graphrag_retrieve") as span:
    span.set_attribute("retriever", "hybrid_plus_graph")
    span.set_attribute("query_type", query_type)
    span.set_attribute("candidate_count", len(candidates))
    span.set_attribute("graph_hops", max_hops)
    span.set_attribute("reranker", reranker_name)
```

Track at least:

- retriever selected by the router
- AI Search index name and query type
- graph store and schema version
- Text2Cypher prompt version and generated Cypher
- candidate counts before/after reranker
- answer citations, entity IDs, and relationship IDs

## Operational Checklist

- **Govern source data in Unity Catalog.** Keep entity and relationship source
  tables in UC, with owners and lineage back to raw documents or structured
  systems.
- **Version graph schemas.** Changes to labels, relationship names, or primary
  keys can break Text2Cypher and traversal prompts.
- **Rebuild derived indexes safely.** Rebuild AI Search indexes, graph indexes,
  and reranker datasets after source schema changes.
- **Use Databricks Apps resources for credentials.** Do not hardcode graph store,
  AI Search, Model Serving, or SQL credentials in app code.
- **Prefer read-only graph access.** Graph write pipelines should be separate
  jobs with tests, not agent runtime actions.
- **Monitor drift.** Track entity-linking quality, orphan nodes, stale edges,
  retrieval failure categories, and latency/cost by retriever.

## Failure Modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Correct document found, wrong relationship answer | Graph expansion too broad or stale edge | Add edge provenance, tighter hop limits, and relationship filters |
| Graph answer is correct but uncited | Missing source_doc_id or chunk IDs on graph nodes | Store provenance on every entity and relationship |
| Text2Cypher times out | Unbounded path or missing indexes | Validate query, add limits, index common properties |
| Hybrid beats GraphRAG | Relationships are not needed | Keep AI Search hybrid; do not ship graph complexity |
| Reranker improves quality but misses SLA | Candidate set too large or model too slow | Lower k, cache, or move reranker to Model Serving with clear p95 budget |

## Promotion Bar

Ship GraphRAG only when it has evidence over baseline:

- Better groundedness or context sufficiency in MLflow evaluation.
- Better relationship/path recall on graph-specific questions.
- Acceptable latency and cost at p95.
- Clear provenance from answer to documents, entities, and relationships.
- Safe Text2Cypher validation or no generated graph query path at all.
