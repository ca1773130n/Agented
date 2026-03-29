# Implementation Plan: Auto-Evolving Agent Memory

## Phase 1: Vector Embedding Store + Hybrid Retrieval

### 1.1 Add sentence-transformers dependency
- File: `backend/pyproject.toml`
- Add `sentence-transformers>=3.0.0` and `numpy>=1.24.0`

### 1.2 Create embedding service
- File: `backend/app/services/embedding.py` (new)
- Module-level singleton `_model: SentenceTransformer | None = None`
- `get_model()` → lazy-loads `nomic-embed-text-v1.5` on first call
- `embed_texts(texts: list[str]) -> list[list[float]]` → batch embed
- `embed_text(text: str) -> list[float]` → single embed
- `cosine_similarity(a, b) -> float` → numpy dot product

### 1.3 Add embedding schema
- File: `backend/app/db/schema.py`
- Add `memory_embeddings` table after line 2124 (after FTS triggers)
- Columns: id, message_id (FK), embedding (BLOB), model, dimension, created_at
- Index on message_id

### 1.4 Add vector recall to agent_memory.py
- File: `backend/app/db/agent_memory.py`
- Add `embed_and_store(message_id, content)` → embeds + inserts BLOB
- Add `vector_recall(query, resource_id, thread_id, top_k)` → numpy cosine search
- Add `hybrid_recall(...)` → combines FTS5 + vector via Reciprocal Rank Fusion
  - RRF: `score = alpha/(k + rank_fts) + (1-alpha)/(k + rank_vec)`, k=60

### 1.5 Update RecallQuery model
- File: `backend/app/models/agent_memory.py`
- Add fields: `search_mode`, `alpha`, `include_cross_thread`
- Add `SearchMode` enum: hybrid, fts, vector

### 1.6 Update recall endpoint
- File: `backend/app/routes/agent_memory.py`
- Route recall to appropriate search based on `search_mode`
- Return enriched response with `relevance_score`

### 1.7 Update frontend types & API
- File: `frontend/src/services/api/agent-memory.ts`
- Add `search_mode`, `alpha` to recall params
- Add `relevance_score` to response types

### 1.8 Backend tests
- File: `backend/tests/test_agent_memory_vector.py` (new)
- Test embedding service singleton, embed/store, vector recall, hybrid RRF

### 1.9 Frontend tests
- Update existing memory tests if any recall assertions need new fields

---

## Phase 2: Knowledge Graph

### 2.1 Add KG schema
- File: `backend/app/db/schema.py`
- `kg_entities` table: id, agent_id, name, entity_type, properties (JSON), mention_count, importance_score, first_seen, last_seen
- `kg_relations` table: id, agent_id, source_id, target_id, relation_type, properties, confidence, mention_count, first_seen, last_seen
- Indexes: (agent_id, name), (source_id), (target_id), (agent_id) on relations

### 2.2 Add KG ID generators
- File: `backend/app/db/ids.py`
- `generate_kg_entity_id()` → `kge-` prefix
- `generate_kg_relation_id()` → `kgr-` prefix

### 2.3 Create KG database module
- File: `backend/app/db/knowledge_graph.py` (new)
- `upsert_entity(agent_id, name, entity_type, properties)` → insert or increment mention_count
- `upsert_relation(agent_id, source_name, target_name, relation_type, confidence)`
- `get_entity(agent_id, name)` → single entity lookup
- `list_entities(agent_id, entity_type?, min_importance?)` → filtered list
- `traverse_graph(agent_id, entity_name, hops=1)` → BFS traversal returning subgraph
- `search_entities(agent_id, query)` → LIKE search on entity names
- `get_entity_context(agent_id, entity_names)` → natural language summary of entity relationships

### 2.4 Create entity extraction service
- File: `backend/app/services/entity_extraction.py` (new)
- `extract_entities_from_text(text)` → returns list of `{name, type, relations}`
- Uses structured LLM output via the agent's configured model (or fallback regex patterns)
- Designed to run async via APScheduler

### 2.5 Add extraction_pending column
- File: `backend/app/db/schema.py`
- Add `extraction_pending INTEGER DEFAULT 1` to memory_messages table

### 2.6 Add async extraction job
- File: `backend/app/__init__.py`
- Register APScheduler job: process pending messages for entity extraction
- Interval: every 30 seconds, batch of 10 messages

### 2.7 Create KG Pydantic models
- File: `backend/app/models/knowledge_graph.py` (new)
- `KGEntity`, `KGRelation`, `KGSubgraph`, `EntityExtractionResult`

### 2.8 Create KG API routes
- File: `backend/app/routes/knowledge_graph.py` (new)
- `GET /admin/agents/<id>/knowledge/entities` — list entities
- `GET /admin/agents/<id>/knowledge/entities/<entity_id>` — entity detail + relations
- `GET /admin/agents/<id>/knowledge/graph` — subgraph query (seed entity, hops)
- `GET /admin/agents/<id>/knowledge/stats` — entity count, relation count, last extraction

### 2.9 Register KG blueprint
- File: `backend/app/__init__.py`
- Register `knowledge_graph_bp`

### 2.10 Backend tests
- File: `backend/tests/test_knowledge_graph.py` (new)

### 2.11 Frontend KG API client
- File: `frontend/src/services/api/knowledge-graph.ts` (new)

---

## Phase 3: CRAG Orchestrator + Enhanced Recall

### 3.1 Create memory orchestrator service
- File: `backend/app/services/memory_orchestrator.py` (new)
- `orchestrated_recall(query, agent_id, thread_id, config)` → main entry point
- Calls hybrid_recall → evaluates relevance → routes to correct/ambiguous/incorrect paths
- Correct: return results directly
- Ambiguous: augment with KG traversal + broader cross-thread search
- Incorrect: fallback to working memory + recent messages

### 3.2 Add threshold-based evaluation
- In memory_orchestrator: percentile-based thresholds on retrieval scores
- No LLM call by default — pure score-based routing
- Optional LLM evaluator behind `use_crag=True` flag

### 3.3 Integrate KG context into recall
- Extend hybrid_recall to include KG entity matches as a third signal
- Three-way RRF: FTS + Vector + KG entity relevance

### 3.4 Update recall endpoint to use orchestrator
- File: `backend/app/routes/agent_memory.py`
- When `search_mode=hybrid`, route through orchestrator
- Add `use_crag`, `graph_hops`, `include_cross_thread` to RecallQuery

### 3.5 Update RecallResponse
- Add `retrieval_evaluation` (correct/ambiguous/incorrect)
- Add `related_entities` list
- Add `graph_context` string

### 3.6 Frontend: recall response UI updates
- Show evaluation badge (colored dot)
- Show related entities as inline tags
- Show graph_context in collapsible section

### 3.7 Backend tests
- File: `backend/tests/test_memory_orchestrator.py` (new)

---

## Phase 4: Auto-Evolution Engine

### 4.1 Memory consolidation service
- File: `backend/app/services/memory_evolution.py` (new)
- `consolidate_thread(agent_id, thread_id)` → summarize thread, extract key insights
- `merge_duplicate_entities(agent_id)` → fuzzy name matching, merge
- Trigger: message_count % 50 == 0 AND last_consolidation > 1 hour ago

### 4.2 Knowledge decay
- In memory_evolution: `apply_decay(agent_id)`
- Exponential: `importance *= exp(-lambda * days_since_seen)`
- `effective_lambda = base_lambda / log(1 + mention_count)`, base 30-day half-life
- Archive entities with importance < 0.1

### 4.3 Recall-based promotion
- In agent_memory.py: when entities appear in recall results, increment mention_count + reset last_seen

### 4.4 Cross-thread synthesis
- In knowledge_graph.py: `find_related_threads(agent_id, thread_id)` via shared entities
- Add route: `GET /admin/agents/<id>/memory/threads/<tid>/related`

### 4.5 Add consolidation schedule
- File: `backend/app/__init__.py`
- APScheduler job: run decay every 24 hours
- APScheduler job: check consolidation triggers every 5 minutes

### 4.6 Add consolidation tracking
- Schema: `memory_consolidation_log` table (id, agent_id, thread_id, type, summary, created_at)

### 4.7 Backend tests
- File: `backend/tests/test_memory_evolution.py` (new)

---

## Phase 5: Frontend Integration + Config UI

### 5.1 Update MemoryConfig type
- File: `frontend/src/services/api/agent-memory.ts`
- Add `vector_search`, `knowledge_graph`, `crag_evaluation`, `cross_thread` toggles

### 5.2 Memory config panel updates
- Add toggle switches for new features in existing agent memory config UI

### 5.3 Knowledge graph entity list component
- Table: name, type, mention_count, importance, last_seen
- Expandable row for relations

### 5.4 Memory health stats card
- Inline stats: entity count, relations, last consolidation, messages since last

### 5.5 Related threads indicator
- In thread list: show related thread count badge

### 5.6 Frontend tests
- Test new components and API integration

### 5.7 Update MemoryConfig backend model
- Add new config fields to `UpdateMemoryConfigBody`
- Update config defaults in routes
