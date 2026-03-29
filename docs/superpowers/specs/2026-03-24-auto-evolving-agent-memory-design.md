# Auto-Evolving Agent Memory with Hybrid RAG + Knowledge Graph

## Problem Statement

Agented's current agent memory system uses FTS5 BM25 lexical search for recall. This has fundamental limitations identified across the research:

1. **No semantic understanding** — FTS5 matches words, not meaning. "car" won't find "automobile"
2. **No relational reasoning** — Cannot traverse entity relationships or answer multi-hop queries
3. **No self-correction** — Retrieval results are used blindly without quality assessment (CRAG paper)
4. **No auto-evolution** — Memory doesn't consolidate, summarize, or refine over time
5. **No cross-thread synthesis** — Knowledge stays siloed within individual threads

## Design Overview

A three-layer memory architecture inspired by the Knowledge Graph book's "LLM sandwiched by formal layers" pattern, CRAG's self-correcting retrieval, and Deep Agents' persistent context management:

```
┌─────────────────────────────────────────────────┐
│                 Agent Runtime                     │
│  (prompt building, conversation, tool execution) │
└────────────────────┬────────────────────────────┘
                     │ recall / save
┌────────────────────▼────────────────────────────┐
│           Memory Orchestrator (CRAG)             │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ Retrieval │ │ Relevance│ │   Knowledge      │ │
│  │ Router    │ │ Evaluator│ │   Refinement     │ │
│  └────┬─────┘ └────┬─────┘ └────────┬─────────┘ │
└───────┼─────────────┼────────────────┼───────────┘
        │             │                │
┌───────▼─────────────▼────────────────▼───────────┐
│              Hybrid Retrieval Layer               │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │  FTS5    │ │  Vector  │ │  Knowledge Graph │  │
│  │  (BM25)  │ │  (cosine)│ │  (entity-rel)    │  │
│  └──────────┘ └──────────┘ └──────────────────┘  │
└──────────────────────┬───────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────┐
│            Auto-Evolution Engine                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ Entity   │ │ Memory   │ │  Knowledge       │  │
│  │ Extractor│ │ Consolid.│ │  Decay/Promote   │  │
│  └──────────┘ └──────────┘ └──────────────────┘  │
└──────────────────────────────────────────────────┘
```

## Architecture Components

### 1. Vector Embedding Store (New)

Adds semantic search alongside existing FTS5.

**Schema additions:**
```sql
CREATE TABLE memory_embeddings (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL REFERENCES memory_messages(id),
    embedding BLOB NOT NULL,          -- float32 array serialized
    model TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    dimension INTEGER NOT NULL DEFAULT 384,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(message_id, model)
);
CREATE INDEX idx_embeddings_message ON memory_embeddings(message_id);
```

**Implementation:**
- Use `sentence-transformers` with `all-MiniLM-L6-v2` (384 dims, fast, no API key needed)
- Embed on save, store as BLOB in SQLite
- Cosine similarity search via numpy (no external vector DB dependency)
- Hybrid scoring: `final_score = alpha * bm25_norm + (1-alpha) * cosine_sim` where alpha defaults to 0.4

### 2. Knowledge Graph (New)

Lightweight property graph stored in SQLite for entity-relationship tracking.

**Schema:**
```sql
CREATE TABLE kg_entities (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,        -- person, concept, tool, project, etc.
    properties TEXT DEFAULT '{}',     -- JSON
    mention_count INTEGER DEFAULT 1,
    importance_score REAL DEFAULT 0.5,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_id, name, entity_type)
);

CREATE TABLE kg_relations (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    source_id TEXT NOT NULL REFERENCES kg_entities(id),
    target_id TEXT NOT NULL REFERENCES kg_entities(id),
    relation_type TEXT NOT NULL,      -- uses, knows, depends_on, related_to, etc.
    properties TEXT DEFAULT '{}',     -- JSON
    confidence REAL DEFAULT 0.5,
    mention_count INTEGER DEFAULT 1,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_kg_entities_agent ON kg_entities(agent_id);
CREATE INDEX idx_kg_relations_source ON kg_relations(source_id);
CREATE INDEX idx_kg_relations_target ON kg_relations(target_id);
CREATE INDEX idx_kg_relations_agent ON kg_relations(agent_id);
```

**Graph queries:**
- 1-hop: Direct entity relationships
- 2-hop: Entity → relation → entity → relation → entity (multi-hop reasoning)
- Subgraph extraction: All entities/relations within N hops of a seed entity

### 3. CRAG-Style Memory Orchestrator (New)

Self-correcting retrieval inspired by CRAG paper (arXiv 2401.15884).

**Flow:**
```
Query → Hybrid Retrieval (FTS5 + Vector + KG) → Relevance Evaluator
    ├── CORRECT (score > 0.7): Use results directly
    ├── AMBIGUOUS (0.3-0.7): Augment with KG traversal + broader search
    └── INCORRECT (< 0.3): Fallback to working memory + recent context
→ Knowledge Refinement: Extract only relevant fragments
→ Return refined context to agent
```

**Evaluator** uses a lightweight LLM prompt (or the agent's own model) to score retrieval relevance:
```python
class RetrievalEvaluation(BaseModel):
    relevance: Literal["correct", "ambiguous", "incorrect"]
    confidence: float  # 0-1
    reasoning: str
```

For cost efficiency, the evaluator is optional and can be disabled — falling back to score-threshold-based routing using the hybrid retrieval scores directly.

### 4. Auto-Evolution Engine (New)

Automated knowledge extraction and memory refinement.

**4a. Entity Extraction (on message save):**
- After each conversation message is saved, extract entities and relations
- Use LLM-based extraction with structured output
- Upsert into knowledge graph (increment mention_count, update last_seen)

**4b. Memory Consolidation (periodic):**
- Triggered after N messages or on schedule
- Summarize thread into key insights
- Merge duplicate entities (fuzzy name matching)
- Promote frequently-referenced knowledge (increase importance_score)

**4c. Knowledge Decay (periodic):**
- Decrease importance_score for entities not seen recently
- Archive (soft-delete) entities below threshold
- Prevents unbounded growth while retaining important knowledge

**4d. Cross-Thread Synthesis:**
- When saving to a thread, check if entities overlap with other threads
- Create cross-references in KG relations
- Enable "what do we know about X across all conversations?" queries

### 5. Enhanced Recall API

Extends existing `/admin/agents/<id>/memory/recall` endpoint.

**New RecallQuery fields:**
```python
class RecallQuery(BaseModel):
    thread_id: Optional[str] = None
    q: str
    top_k: int = 5
    message_range: int = 2
    # New fields:
    search_mode: Literal["hybrid", "fts", "vector", "graph"] = "hybrid"
    use_crag: bool = True           # Enable self-correcting retrieval
    graph_hops: int = 1             # KG traversal depth
    include_cross_thread: bool = False  # Search across all threads
    alpha: float = 0.4              # FTS vs vector weight
```

**Response additions:**
```python
class RecallResult(BaseModel):
    messages: List[MemoryMessage]
    # New fields:
    relevance_score: float
    retrieval_evaluation: Optional[str]  # correct/ambiguous/incorrect
    related_entities: List[KGEntity]
    graph_context: Optional[str]  # Serialized subgraph as natural language
```

### 6. Frontend Updates

- Memory config panel: toggle vector search, KG extraction, CRAG evaluation
- Knowledge graph visualization: entity-relation graph view per agent
- Memory evolution timeline: show consolidation events, entity growth

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Embedding model | sentence-transformers (local) | No API key, fast, offline-capable |
| Vector storage | SQLite BLOB + numpy | No new dependencies (no Chroma/FAISS) |
| Graph storage | SQLite tables | Consistent with existing architecture |
| Entity extraction | LLM structured output | Uses agent's own model, no new service |
| CRAG evaluator | Optional LLM or threshold | Cost control — can disable for speed |

## Migration

- All new tables are additive — no schema changes to existing tables
- Existing FTS5 recall continues to work as-is
- Vector embeddings generated lazily (on next recall) or via batch migration
- KG populated incrementally from new conversations

## Dependencies

New Python packages:
- `sentence-transformers>=3.0.0` — embedding model
- `numpy>=1.24.0` — cosine similarity computation (likely already present)

No new system dependencies. No external APIs required.

## Phases

1. **Phase 1: Vector Embedding Store** — Schema, embedding service, hybrid retrieval
2. **Phase 2: Knowledge Graph** — Schema, entity extraction, graph queries
3. **Phase 3: CRAG Orchestrator** — Relevance evaluation, retrieval routing, knowledge refinement
4. **Phase 4: Auto-Evolution Engine** — Consolidation, decay, cross-thread synthesis
5. **Phase 5: Frontend + Integration** — Config UI, KG visualization, memory timeline
