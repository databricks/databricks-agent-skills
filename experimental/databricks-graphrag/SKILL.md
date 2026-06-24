---
name: databricks-graphrag
description: "Design GraphRAG and knowledge-graph augmented retrieval on Databricks. Use when comparing GraphRAG vs traditional RAG, combining AI Search with graph traversal, designing entity/relationship models, evaluating hybrid retrieval quality, or integrating Neo4j/Text2Cypher patterns with Unity Catalog, Databricks Apps, Model Serving, and MLflow."
compatibility: Requires databricks CLI (>= v1.0.0)
metadata:
  version: "0.1.0"
parent: databricks-core
---

# GraphRAG on Databricks

GraphRAG augments retrieval with explicit entities and relationships. Use it when
answers require multi-hop reasoning, exact relationship paths, explainable
provenance, or structured graph constraints that plain chunk retrieval misses.

This skill is an architecture and evaluation guide. Databricks provides the
governed platform spine — Unity Catalog, AI Search, Databricks Apps, Model
Serving, and MLflow evaluation — while graph stores and Text2Cypher libraries are
integration choices, not Databricks-native APIs.

## Critical Rules

- **Start with AI Search hybrid retrieval first.** Establish a measured baseline
  with keyword + vector retrieval, filters, and reranking before adding graph
  complexity.
- **Use GraphRAG only when relationships matter.** If the query only needs
  semantically similar passages, use `databricks-vector-search` / AI Search.
- **Keep graph queries read-only.** Text2Cypher and generated graph traversals
  must run against allow-listed labels, relationship types, and result limits.
- **Evaluate before promoting.** Compare ANN, hybrid, reranker, graph traversal,
  and Text2Cypher with MLflow metrics and groundedness judges.
- **Govern inputs and outputs in Unity Catalog.** Source Delta tables, derived
  entity/relationship tables, AI Search indexes, and model/agent registrations
  should have UC ownership, permissions, lineage, and auditability.

## When to Use

| User asks for | Use this skill? | Why |
|---|---:|---|
| "Should I use GraphRAG or normal RAG?" | Yes | Architecture decisioning and trade-offs |
| "Find related policies, owners, systems, and exceptions" | Yes | Relationship traversal is part of the answer |
| "Build document Q&A over PDFs" | Usually no | Start with Knowledge Assistant or AI Search RAG |
| "Improve retrieval precision for SKUs/error codes" | Maybe | Try AI Search hybrid + filters + reranker first |
| "Generate Cypher from questions" | Yes | Requires Text2Cypher safety guidance |

## Workflow

1. **Define answer shape.** Identify whether the answer needs passages,
   entities, paths, summaries, or calculations.
2. **Build the baseline.** Use AI Search hybrid retrieval with metadata filters
   and optional reranker; measure recall and groundedness.
3. **Model the graph.** If the baseline misses relationships, design entity and
   relationship tables in Unity Catalog before loading an external graph store.
4. **Choose retrieval pattern.** Pick vector-to-graph expansion, full-text to
   graph, Text2Cypher, or a router that chooses among them.
5. **Assemble the app/agent.** Prefer Databricks Apps for custom UX/API agents;
   use Model Serving when deploying custom models, embeddings, or agent endpoints.
6. **Evaluate and operate.** Use MLflow traces, retrieval metrics, groundedness,
   sufficiency, and latency budgets before recommending GraphRAG over simpler RAG.

## Reference Files

| File | Purpose |
|---|---|
| [references/architecture-decisions.md](references/architecture-decisions.md) | Decide when GraphRAG is worth the added complexity |
| [references/retrieval-patterns.md](references/retrieval-patterns.md) | Retrieval patterns for AI Search, Neo4j, Text2Cypher, and routers |
| [references/evaluation-and-operations.md](references/evaluation-and-operations.md) | MLflow evaluation, safety checks, observability, and operations |

## Related Skills

- **databricks-vector-search** — AI Search / Vector Search indexes, hybrid
  search, filters, reranking, and baseline RAG.
- **databricks-apps** — Databricks Apps for custom GraphRAG UX and APIs.
- **databricks-model-serving** — serving LLMs, embeddings, custom rerankers, and
  model/agent endpoints.
- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** —
  MLflow GenAI traces, datasets, scorers, and production monitoring.
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — source
  tables, governance, access control, lineage, and system tables.
- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** — managed
  Knowledge Assistant baseline and supervisor-agent routing comparison.

## Official References

- AI Search: https://docs.databricks.com/aws/en/ai-search/ai-search
- AI Search retrieval quality: https://docs.databricks.com/aws/en/ai-search/retrieval-quality
- Databricks Apps resources: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources
- Model Serving: https://docs.databricks.com/aws/en/machine-learning/model-serving/
- MLflow GenAI evaluation: https://docs.databricks.com/aws/en/mlflow3/genai/eval-monitor/
