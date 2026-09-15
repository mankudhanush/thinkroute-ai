# ThinkNRoute — Context Engine Redesign

**Scope:** Redesign *only* the Context Retrieval System. No changes to routing logic,
provider integration, frontend, or existing public APIs. Everything below is **additive**
and plugs into the current `app/services/memory/` package behind its existing seams.

---

## 0. Root-cause diagnosis (why retrieval fails today)

The current engine is well-built but it **skips the single most important step**: it never
asks *what kind of query this is* before deciding how to retrieve. It jumps straight to
domain-based **threading** + **lexical** scoring. That one gap explains every reported bug.

### Example 1 & 2 — "Explain the solution again" / "Explain again" → *No context*

Traced through the real code:

1. [`context_analyzer.py`](../app/services/memory/context_analyzer.py#L30-L35) lists
   `"explain"` in `_NEW_TOPIC_MARKERS`. The prompt starts with `explain` and matches **no**
   follow-up marker → `likely_new_topic=True`, `is_followup=False`.
2. [`thread_manager.py`](../app/services/memory/thread_manager.py#L45-L63) `_domain()` maps
   `"explain …"` to the **`knowledge`** domain (via `_KNOWLEDGE_OPENERS`). The prior
   *"Build a REST API"* turn was domain **`software`**.
3. [`_pick_thread`](../app/services/memory/thread_manager.py#L168-L202): there is no
   existing `knowledge` thread → returns `None` → **new thread**, `is_new=True`.
4. [`memory_engine.py`](../app/services/memory/memory_engine.py#L86-L95): `is_new=True`
   means `selected = []` → `used_count=0` → **"No previous context used."**

> **The verb "explain" is being treated as a brand-new knowledge topic, so a follow-up that
> literally says "again" is severed from the thread it refers to.** `"Explain again"` (2 words)
> also isn't caught as a `_PURE_REFERENCE` because that check requires the *whole* stripped
> string to equal a reference phrase, and `"explain again"` doesn't.

### Example 3 — "What was my first prompt?" → retriever returns the question itself

There is **no notion of a meta / conversation-memory query**. The prompt is scored
lexically like any other; its own keywords `{first, prompt}` match nothing meaningful, so the
retriever ([`memory_retriever.py`](../app/services/memory/memory_retriever.py#L74-L83))
falls back to "keep the most relevant turns in-thread" — which is noise. The system has no
path that says *"this is a structured question about the conversation itself → answer it from
the DB, ordered by `id ASC`, LIMIT 1."*

### Systemic issues

| Symptom | Cause |
|---|---|
| Follow-ups fail | Query type never classified; "explain/why/compare" openers hijacked into `knowledge` domain and split off |
| Memory questions fail | No structured/SQL path; meta queries scored lexically |
| Semantic misses ("add JWT" ↛ "REST API") | Only `LexicalSimilarityScorer` exists; zero keyword overlap ⇒ zero signal |
| No provider continuity | No provider-affinity concept anywhere in the packet or router |

**The fix is not to tune thresholds. It is to add the missing Query Analyzer stage and route
each query type to the retrieval strategy that actually fits it — a hybrid engine.**

---

## 1. High-level architecture

The current pipeline (`build_context`) is:

```
prompt + history → analyze → thread → retrieve (lexical) → packet
```

The redesigned pipeline inserts a **Query Analyzer** and a **Strategy Dispatcher**, keeping
every existing component as one of the pluggable strategies:

```
                         ┌──────────────────────────────────────────┐
   User Prompt ─────────▶│              QueryAnalyzer                │  (<1 ms, rules-first)
                         │  query_type · needs_context · intent      │
                         │  complexity · confidence                  │
                         └───────────────────┬──────────────────────┘
                                             │  QueryClassification
                                             ▼
                         ┌──────────────────────────────────────────┐
                         │           RetrievalDispatcher             │
                         │   picks a strategy by query_type          │
                         └───────────────────┬──────────────────────┘
        ┌────────────┬────────────┬──────────┼───────────┬───────────────┐
        ▼            ▼            ▼           ▼           ▼               ▼
   NewTask      FollowUp     Memory      Semantic    Comparison     Correction
  (no retr.)  (recent/     (SQL /      (embeddings  (dual-thread)  (last turn)
              thread)      structured) + lexical)
        └────────────┴────────────┴──────────┬───────────┴───────────────┘
                                             ▼
                         ┌──────────────────────────────────────────┐
                         │             ContextBuilder                │
                         │  clean packet + provider_affinity hint    │
                         └───────────────────┬──────────────────────┘
                                             ▼
                    Existing Routing Engine ▸ Selected Provider  (UNCHANGED)
```

**Key principle:** `MemoryEngine.build_context()` keeps the *same signature and return type*
(`tuple[ContextPacket, float]`). Callers in [`chat_service.py:50-51`](../app/services/chat_service.py#L50-L51)
and [`auto_router.py:72-73`](../app/services/auto_router.py#L72-L73) do **not** change.
All new logic lives *inside* the memory package.

---

## 2. Query Analyzer design

New module: `app/services/memory/query_analyzer.py`. **Rules-first, deterministic, no I/O,
sub-millisecond.** It never calls a model on the hot path (protects the <100 ms budget).
`qwen3:4b` is *optional* and used only as a tiebreaker below a confidence floor (see §11 Phase 4).

### Output contract

```python
class QueryType(str, Enum):
    NEW_TASK       = "new_task"
    FOLLOW_UP      = "follow_up"
    MEMORY         = "conversation_memory"
    SEMANTIC       = "semantic"
    COMPARISON     = "comparison"
    CORRECTION     = "correction"

@dataclass(frozen=True)
class QueryClassification:
    query_type: QueryType
    needs_context: bool          # False ⇒ skip retrieval entirely
    retrieval: RetrievalStrategy # enum: NONE | RECENT | THREAD | SQL | VECTOR | DUAL
    intent: str                  # reuse existing PromptAnalysis signal where possible
    complexity: str              # "low" | "medium" | "high"
    confidence: float            # 0..1
    signals: tuple[str, ...]     # matched markers, for explainability in ContextInfo
```

### Classification rules (evaluated in priority order)

Order matters — the first confident match wins. This ordering is what fixes the
"explain hijack".

1. **MEMORY (highest priority).** Regexes over meta-patterns:
   `what (was|were) my (first|last|previous|earlier) …`, `what did i (ask|say) …`,
   `which provider …`, `how many (prompts|messages|questions) …`, `what have we discussed`,
   `summarize (our|this) (chat|conversation)`. → `retrieval=SQL`, `needs_context=True`,
   confidence ≥ 0.9. **This must be checked before the NEW_TASK/`explain` rules**, otherwise
   "explain what I asked earlier" is misread as a new explain-task.

2. **CORRECTION.** `no,? that'?s wrong`, `that'?s (not right|incorrect)`, `fix the (previous|last|above)`,
   `you (made a mistake|got it wrong)`, `undo`, `revert`. → `retrieval=RECENT` (last interaction).

3. **COMPARISON.** `compare (this|it|that) (with|to)`, `vs the previous`, `difference from the last`,
   `which (is|was) better`. → `retrieval=DUAL`.

4. **FOLLOW_UP.** The reference/continuation markers already curated in
   [`context_analyzer.py`](../app/services/memory/context_analyzer.py#L10-L28)
   (`continue`, `again`, `improve it`, `why`, `simplify`, `explain … again`, `add …`, …).
   **Critical change:** `"explain"`/`"why"` **immediately followed or preceded by a reference
   token** (`again`, `that`, `this`, `it`, `the solution`, `more`) is a FOLLOW_UP, *not* a new
   topic. A bare `"Why?"` or `"Explain again"` is a FOLLOW_UP. → `retrieval=THREAD` (stick to
   active thread; see §3).

5. **SEMANTIC.** Has real topical keywords, attaches to ongoing work but not via an explicit
   reference (`add authentication`, `implement JWT`, `create login`). → `retrieval=VECTOR`
   (embedding search, lexical fallback).

6. **NEW_TASK (default / fallthrough).** A self-contained instruction with a fresh topic and
   no reference/continuation signal (`Build a website.`). → `retrieval=NONE`,
   `needs_context=False`.

Reuse — do **not** duplicate — the existing `PromptAnalysis`, `similarity.keywords()`, and the
domain heuristic. The Query Analyzer *wraps* `ContextAnalyzer`; it adds the meta/correction/
comparison layer and the priority ordering the current code lacks.

---

## 3. Retrieval strategies

Each strategy implements a tiny interface so the dispatcher is trivial and each path is
independently testable:

```python
class Retriever(Protocol):
    def retrieve(self, ctx: RetrievalContext) -> list[ScoredMessage]: ...
```

| query_type | Strategy | Method | Notes |
|---|---|---|---|
| `NEW_TASK` | `NullRetriever` | **no retrieval** | returns `[]`; packet = current prompt only |
| `FOLLOW_UP` | `ThreadRetriever` | **recent + thread** | reuse existing `ThreadManager`/`MemoryRetriever`, but **force the active thread** and bypass the domain split (fixes Ex.1/2) |
| `MEMORY` | `StructuredRetriever` | **SQL** | deterministic query over `chat_messages`; see §3.1 |
| `SEMANTIC` | `SemanticRetriever` | **vector** | embedding cosine over conversation vectors; lexical fallback if embeddings unavailable |
| `COMPARISON` | `DualRetriever` | **vector + thread** | pull the *current* subject AND the *previous* solution (two anchors) |
| `CORRECTION` | `LastTurnRetriever` | **recent** | last user+assistant pair of the active thread, verbatim |

### 3.1 Structured (SQL) retrieval — the missing memory path

`StructuredRetriever` answers meta-questions **from the database, not from similarity**. It maps
the matched MEMORY sub-pattern to an exact query:

```python
# "what was my first prompt?"
SELECT content FROM chat_messages
WHERE conversation_id = ? AND role = 'user'
ORDER BY id ASC LIMIT 1;

# "what did I ask earlier / last?"  → ORDER BY id DESC, skip the current turn
# "how many prompts have I sent?"   → SELECT COUNT(*) ... role='user'
# "which provider answered [that]?" → SELECT provider,model ... role='assistant' ORDER BY id DESC LIMIT 1
```

The result is wrapped as a **structured facts block** and placed in the packet as a system/
context turn, e.g.:

```
[conversation facts]
Your first message in this conversation was: "Build a REST API."
```

The selected provider then phrases the final answer naturally. (Optionally, for pure count/
lookup questions you can short-circuit and answer without a provider call — a fast path — but
routing the fact through the provider keeps the response voice consistent and touches no
routing code.)

### 3.2 Follow-up fix (Ex. 1 & 2)

For `FOLLOW_UP`, the dispatcher calls `ThreadManager` with a new flag
`force_active_thread=True`. In [`_pick_thread`](../app/services/memory/thread_manager.py#L168-L202)
today, a follow-up already sticks to `current` **only when `current.domain == domain`**. Because
`"explain …"` recomputes `domain="knowledge"`, that guard fails. The fix: when the Query
Analyzer has already decided this is a FOLLOW_UP/CORRECTION, **domain is not recomputed** — the
active thread is authoritative. One flag, no rewrite of the threading algorithm.

---

## 4. Context Builder

Keep [`ContextPacketBuilder`](../app/services/memory/context_packet_builder.py) as-is and
extend it additively:

- **Lean by default.** Continue returning only the relevant prior *user* turns
  (`include_responses=False`) to avoid token explosion, but **auto-enable assistant replies**
  for `FOLLOW_UP`, `CORRECTION`, and `COMPARISON`, where the model *needs* to see what it
  previously produced ("explain the solution again" is meaningless without the solution).
- **Facts block** for `MEMORY` (see §3.1) — a single short synthetic turn, not raw history.
- **Budget guard.** Cap the packet at a token budget (e.g. ~1.5k tokens); truncate lowest-score
  turns first. Prevents a long thread from blowing the prompt.
- **Provider affinity hint.** Add two optional fields to `ContextPacket`:
  `preferred_provider: ProviderId | None` and `affinity_reason: str`. Populated from the last
  assistant turn of the active thread when `query_type ∈ {FOLLOW_UP, CORRECTION, COMPARISON}`.
  This is a *hint only* — see §8.

`ContextPacket.to_chat_turns()` stays the contract the providers consume, so provider adapters
are untouched.

---

## 5. Required database changes

**Schema stays backward-compatible — additive only, matching the existing idempotent
`_migrate()` pattern in [`database.py:82-91`](../app/database/database.py#L82-L91).**

You already have `thread_id` and `keywords` columns. Add embedding storage. Two options:

**Recommended — a sibling table (keeps `chat_messages` clean, easy to backfill/rebuild):**

```sql
CREATE TABLE IF NOT EXISTS message_embeddings (
    message_id   INTEGER PRIMARY KEY REFERENCES chat_messages(id) ON DELETE CASCADE,
    model        TEXT    NOT NULL,          -- embedding model id (for re-embed safety)
    dim          INTEGER NOT NULL,
    vector       BLOB    NOT NULL,          -- float32 little-endian
    created_at   TEXT    NOT NULL
);
```

- Nullable-by-absence: legacy messages simply have no row → `SemanticRetriever` falls back to
  lexical for them, then they get embedded lazily on next access. **Zero downtime, no
  destructive migration.**
- If/when you adopt `sqlite-vec` (§6), add a `vec0` virtual table alongside; the BLOB table
  remains the source of truth.

No change to `chat_messages` beyond what already exists. No change to any other table.

---

## 6. Vector database recommendation

**Prefer a tiered, local, zero-infra approach** — most conversations are small, so a heavy
vector DB is unjustified overhead:

1. **Default: in-process NumPy brute force.** Load the conversation's vectors (a conversation
   rarely exceeds a few hundred messages), one `float32` matrix, cosine via a single matmul.
   For < ~1–2k vectors this is **sub-5 ms** and needs no new dependency beyond NumPy. This
   alone covers essentially all real ThinkNRoute conversations.

2. **Scale path: [`sqlite-vec`](https://github.com/asg017/sqlite-vec).** A single-file SQLite
   extension — *no new service, no Docker, stays inside your existing DB*. Ideal because
   ThinkNRoute is already SQLite-native. Enables `WHERE conversation_id = ? ORDER BY
   distance` KNN when a conversation grows large or you later want cross-conversation memory.

**Avoid** for this project: Chroma/Qdrant/Weaviate/pgvector — all introduce a server or a new
datastore, contradicting the "lightweight local" and "minimal changes" goals.

> Recommendation: ship the NumPy scorer first (Phase 2), gate `sqlite-vec` behind a config flag
> for later scale. Same `SemanticRetriever` interface either way.

---

## 7. Embedding model recommendation

Local, CPU-friendly, no GPU, no PyTorch if possible:

| Option | Dim | Size | Notes |
|---|---|---|---|
| **`BAAI/bge-small-en-v1.5` via [`fastembed`](https://github.com/qdrant/fastembed)** ✅ | 384 | ~130 MB | **Recommended.** ONNX runtime, *no torch*, ~5–15 ms/query CPU. `pip install fastembed`, that's it. |
| `all-MiniLM-L6-v2` via `sentence-transformers` | 384 | ~90 MB | Great quality but pulls in torch (~heavy install). |
| **Ollama `nomic-embed-text`** | 768 | — | **Zero new Python deps** — you already run Ollama for `qwen3:4b`. One extra `/api/embeddings` call (~10–30 ms local). Attractive if you want no new pip packages at all. |

**Recommendation:** `fastembed` + `bge-small-en-v1.5` for a self-contained, torch-free, fast
default. If you'd rather add *nothing* new to `requirements.txt`, use Ollama
`nomic-embed-text` — it reuses infrastructure that's already running and is fully local.

Wrap whichever you pick behind the **existing seam**: implement `SimilarityScorer` from
[`similarity.py:87-99`](../app/services/memory/similarity.py#L87-L99) as
`EmbeddingSimilarityScorer` and inject it into `MemoryEngine`. The protocol was *explicitly
designed for this* ("this is the seam for semantic vector search" — comment already in the
file). Keep `LexicalSimilarityScorer` as the guaranteed fallback.

---

## 8. Provider affinity (FastAPI / router integration)

Requirement: on `Explain again` / `Continue` / `Improve this` / `Fix this`, **prefer the
provider that produced the previous response** unless there's a strong reason to switch.

Implementation that touches **no routing logic**:

- `ContextBuilder` sets `packet.preferred_provider` (from the last assistant turn of the active
  thread) for the affinity query types.
- In [`auto_router.py`](../app/services/auto_router.py#L79-L99), the routing engine still
  computes `primary` and `failover_chain` exactly as today. **Only reorder the chain** so that,
  when `packet.preferred_provider` is set and connected, it is tried first:

```python
chain = routing_engine.failover_chain(primary)
if packet.preferred_provider:
    chain = [packet.preferred_provider] + [p for p in chain if p != packet.preferred_provider]
```

This is a *candidate reordering*, not a routing-rule change — the engine, classifier, and
failover mechanics are untouched. Manual mode (`chat_service.py`) already fixes the provider,
so affinity is naturally satisfied there.

**"Strong reason to switch" guard:** if the classifier marks the follow-up as `high` complexity
/ `requires_long_context` and the previous provider is `OLLAMA`, keep the routing engine's
choice (don't pin a small local model to a now-heavy task). Encode this as one predicate in the
builder before setting `preferred_provider`.

---

## 9. New modules / files to create

All under `app/services/memory/` (no files elsewhere are modified except the two additive hooks
in §8 and the additive migration in §5):

```
app/services/memory/
  query_analyzer.py        # NEW — QueryType, QueryClassification, rule engine (§2)
  strategies/
    __init__.py            # NEW — Retriever protocol + dispatcher table
    null_retriever.py      # NEW — NEW_TASK
    thread_retriever.py    # NEW — FOLLOW_UP (wraps existing ThreadManager/MemoryRetriever)
    structured_retriever.py# NEW — MEMORY (SQL) (§3.1)
    semantic_retriever.py  # NEW — SEMANTIC (vector; lexical fallback)
    dual_retriever.py      # NEW — COMPARISON
    last_turn_retriever.py # NEW — CORRECTION
  embedding_scorer.py      # NEW — EmbeddingSimilarityScorer implements SimilarityScorer (§7)
  vector_store.py          # NEW — NumPy brute-force store; sqlite-vec adapter behind flag (§6)
```

**Reused unchanged:** `context_analyzer.py`, `thread_manager.py`, `memory_retriever.py`,
`context_packet_builder.py`, `similarity.py`, `context_cache.py`.
**Extended additively:** `memory_engine.py` (dispatch), `context_packet_builder.py` (facts block +
affinity fields), `database.py` (`_migrate` adds `message_embeddings`), `storage_service.py`
(embedding read/write + a couple of structured queries), `schemas.py` (optional new
`ContextInfo` fields).

---

## 10. Folder structure (after)

```
backend/app/services/memory/
├── __init__.py
├── memory_engine.py           # facade — now dispatches by QueryClassification
├── query_analyzer.py          # ← NEW: the missing "what kind of query" stage
├── context_analyzer.py        # (kept) prompt-only signal extraction
├── thread_manager.py          # (kept) + force_active_thread flag
├── memory_retriever.py        # (kept) lexical in-thread scoring
├── context_packet_builder.py  # (kept) + facts block + affinity hint
├── context_cache.py           # (kept) LRU
├── similarity.py              # (kept) LexicalSimilarityScorer + protocol
├── embedding_scorer.py        # ← NEW: EmbeddingSimilarityScorer (same protocol)
├── vector_store.py            # ← NEW: NumPy / sqlite-vec
└── strategies/                # ← NEW package: one file per retrieval strategy
    ├── __init__.py
    ├── null_retriever.py
    ├── thread_retriever.py
    ├── structured_retriever.py
    ├── semantic_retriever.py
    ├── dual_retriever.py
    └── last_turn_retriever.py
```

---

## 11. Step-by-step implementation plan

**Phase 0 — Safety net (no behaviour change).**
Add golden tests that reproduce the three failing examples against today's engine (they should
fail), so every later phase is measured against real regressions/fixes.

**Phase 1 — Query Analyzer + dispatch (fixes Ex. 1, 2, 3; no embeddings yet).**
- Add `query_analyzer.py` and the `strategies/` package.
- `MemoryEngine.build_context` calls the analyzer, then dispatches. `NEW_TASK→Null`,
  `FOLLOW_UP→Thread(force_active)`, `MEMORY→Structured(SQL)`, everything else → existing lexical
  path for now. Ex.1/2/3 turn green here **with zero new dependencies**.

**Phase 2 — Semantic retrieval.**
- Add `embedding_scorer.py`, `vector_store.py`, `message_embeddings` migration.
- Backfill lazily: embed on write, and embed-on-read for legacy rows.
- Wire `SemanticRetriever`; lexical remains the fallback when a vector is missing.

**Phase 3 — Provider affinity + comparison/correction polish.**
- Affinity fields in the packet + the failover reorder hook in `auto_router.py` (§8).
- `DualRetriever` / `LastTurnRetriever`.

**Phase 4 — Optional LLM tiebreaker.**
- Only when `QueryClassification.confidence < floor`, consult `qwen3:4b` (reuse
  `IntentClassifier` infra) to disambiguate query_type. Cached; off the hot path for the 95%
  case. Keeps p99 within budget.

**Phase 5 — Observability.**
- Surface `query_type`, `retrieval`, `confidence`, `affinity_reason` in `ContextInfo` so the
  frontend "Context Used" panel explains *why* — turns the current opaque "No context" into
  "Follow-up → reused 2 msgs from thread t1 (kept Groq)."

---

## 12. Migration strategy (no breakage)

- **API contract preserved.** `ContextInfo`/`ChatResponse`/`AutoChatResponse` only gain
  *optional* fields with defaults → existing frontend keeps working, new fields are ignored
  until the UI opts in.
- **Engine signature preserved.** `build_context()` in/out types are identical; `chat_service`
  and `auto_router` call sites are unchanged in Phase 1.
- **DB migration is additive + idempotent**, following the existing `_migrate()` convention.
  No column drops, no type changes, legacy rows valid.
- **Feature-flag the risky parts.** `settings.context_engine_v2` (default off → on per phase),
  `settings.embeddings_enabled`, `settings.provider_affinity_enabled`. Ship dark, enable
  gradually, instant rollback.
- **Fallback everywhere.** If embeddings are disabled/unavailable → lexical. If the analyzer is
  low-confidence → the existing thread+lexical path (today's behaviour). The system can never do
  *worse* than it does now.

---

## 13. Edge cases & handling

| Edge case | Handling |
|---|---|
| Empty history | Already handled (`build_context` early-returns `is_new_topic=True`); `NEW_TASK` short-circuits. |
| First message is itself a memory query ("what was my first prompt?" as msg #1) | Structured query returns empty → builder emits "This is the start of our conversation." |
| "Explain again" but the last topic *was* a knowledge question | FOLLOW_UP still forces the active thread — correct regardless of domain. |
| Mixed intent ("explain the JWT part again and also add refresh tokens") | Analyzer returns FOLLOW_UP with a SEMANTIC secondary signal → `DualRetriever` (thread anchor + vector for "refresh tokens"). |
| Reference with no antecedent ("continue" as first message) | No active thread → treat as NEW_TASK; builder notes "nothing to continue yet." |
| Preferred provider now disconnected | Affinity is a *hint*; the reorder skips unconnected providers and the normal failover chain proceeds. |
| Long thread → token blow-up | ContextBuilder token-budget guard truncates lowest-score turns first (§4). |
| Legacy rows without embeddings | `SemanticRetriever` lexical-fallback per-message; lazy backfill. |
| Ambiguous query_type, low confidence | Fall back to today's thread+lexical path (never worse than current); optional qwen3 tiebreaker in Phase 4. |
| Very short prompts ("why?", "no.", "more") | Caught by CORRECTION/FOLLOW_UP reference rules *before* keyword scoring, which is exactly where the current engine fails them. |
| Non-English / code-only prompts | Embeddings degrade gracefully; lexical `_TOKEN_RE` already keeps tech tokens (`c++`, `c#`); structured/SQL paths are language-agnostic. |
| Concurrent writes / cache staleness | `_thread_cache` is keyed by `(conversation_id, len(history))` already; embeddings keyed by `message_id` — both invalidate naturally. |

---

## Summary

The engine you have is a solid lexical/threading core — it's just **missing the classification
stage that decides how to retrieve.** Adding a rules-first **Query Analyzer** and a
**strategy dispatcher** (SQL for memory, thread for follow-ups, embeddings for semantic) fixes
all three reported failures, stays under the 100 ms budget (only SEMANTIC touches embeddings),
and plugs into the seams the codebase already exposes (`SimilarityScorer`, the `MemoryEngine`
facade, the additive `_migrate()`). No routing, provider, frontend, or API changes required.
