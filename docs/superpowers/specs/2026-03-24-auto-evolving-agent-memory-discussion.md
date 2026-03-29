# Multi-Backend Discussion: Auto-Evolving Agent Memory

**Date:** 2026-03-24
**Participants:** Backend Architect, ML/RAG Specialist, Frontend/DX Engineer

## Resolved Design Decisions

### 1. Vector Storage: SQLite BLOB + numpy (confirmed)
- Sufficient at agent scale (<50K messages per agent)
- Must use module-level singleton for sentence-transformers model (avoid 500ms cold start per request)
- sqlite-vec as optional upgrade path when per-agent messages exceed 100K

### 2. Embedding Model: nomic-embed-text-v1.5 (changed from MiniLM)
- 768 dims, supports Matryoshka dimensionality reduction to 256 for storage
- Apache-licensed, local, MTEB ~62 (vs MiniLM ~56)
- Better for longer documents (conversation summaries)
- Alternative: bge-small-en-v1.5 (384d) if bundle size is critical

### 3. Hybrid Scoring: Reciprocal Rank Fusion (changed from linear interpolation)
- Formula: `score = alpha/(k + rank_bm25) + (1-alpha)/(k + rank_cosine)`, k=60
- Rank-based, no score normalization needed
- 3-7 NDCG improvement over linear interpolation in BEIR benchmarks
- Remove alpha from public API or keep as advanced tuning knob

### 4. Entity Extraction: Async via APScheduler (changed from sync on save)
- Sync LLM extraction adds 200-800ms per save — unacceptable
- Enqueue background job post-INSERT via APScheduler threadpool
- Add `extraction_pending BOOLEAN DEFAULT TRUE` to memory_messages
- Optional: spaCy NER for fast named entities (sync), LLM for domain-specific (async)

### 5. CRAG Evaluator: Default OFF (confirmed)
- Score-threshold routing as default (no extra LLM call)
- Use percentile-based thresholds rather than fixed values (calibrate on real data)
- LLM evaluator available as opt-in for high-stakes recalls
- Remove `use_crag: True` default from RecallQuery

### 6. Knowledge Graph: SQLite Adjacency List (confirmed)
- Neo4j/Memgraph unnecessary at this scale
- 2-hop traversal via recursive CTEs or two JOINs
- Add missing index: `CREATE INDEX ON kg_entities(agent_id, name)`

### 7. Consolidation Trigger: AND Logic (changed from OR)
- Condition: `message_count % 50 == 0 AND last_consolidation > 1 hour ago`
- Prevents consolidation storms on rapid bursts
- Prevents wasted LLM calls on slow threads

### 8. Knowledge Decay: Exponential with Importance Weighting
- `importance = importance * exp(-lambda * days_since_seen)`
- `lambda = ln(2) / 30` (30-day half-life)
- `effective_lambda = base_lambda / log(1 + mention_count)` — frequent entities decay slower
- Promotion on recall: reset last_seen, increment mention_count
- Archive threshold: `importance_score < 0.1`

### 9. Frontend: Minimal Table-Based UI
- Entity list table (name, type, mentions, importance, last_seen) with expandable relations
- Four config toggles: vector search, KG extraction, CRAG, cross-thread
- Colored dot badges for retrieval evaluation (green/yellow/red)
- Inline stats card per agent (entity count, relations, last consolidation)
- Related threads count via shared entity overlap
