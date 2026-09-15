# ThinkNRoute — Context Engine v2 Architecture Proposal

**Status:** Proposal · **Scope:** Context Retrieval System only · **Non-goals:** routing engine, provider integrations, frontend, existing APIs.

This document proposes a production-grade **Context Engine** that plugs into the *existing* memory package (`app/services/memory/`) with minimal, additive changes. It does **not** rewrite the working modules — it fixes the retrieval decision layer and adds hybrid strategies behind the seams the codebase already exposes.

---

## 0. Root-cause analysis (why retrieval fails today)

The current engine (`MemoryEngine.build_context`) does: `analyze → reconstruct threads → assign thread → lexical retrieve → build packet`. Retrieval quality is bottlenecked by **one missing stage**: the system never classifies *what kind of query* the user is asking. Concretely:

| Example | What happens now | Root cause |
|---|---|---|
| "Explain the solution again" | `is_new_topic = True` → `selected = []` → *"No previous context used."* | `"explain"` is in `_NEW_TOPIC_MARKERS` ([context_analyzer.py](../app/services/memory/context_analyzer.py#L31)) **and** `_KNOWLEDGE_OPENERS` ([thread_manager.py](../app/services/memory/thread_manager.py#L12)). The prompt is forced into the `knowledge` domain, which doesn't match the `software` thread, so a **new thread** is created and retrieval is skipped. The trailing "again" (a continuation signal) is ignored. |
| "Given a string… / Explain again" | Same as above | Same mislabelling of `explain*` as a new topic. |
| "What was my first prompt?" | Retriever returns the message literally containing those words | There is **no concept of a memory query**. It falls through to lexical scoring in `MemoryRetriever.retrieve`, which matches the words *"first / prompt"* against stored messages instead of executing a structured lookup. |

**Conclusion:** the fix is not "add vectors." It is to **classify the query first**, then pick the retrieval method that fits. Vectors are one of *four* strategies, used only for the semantic case.

---

## 1. High-level architecture

```
                        ┌─────────────────────────────────────────────┐
   User Prompt ─────────►            CONTEXT ENGINE v2                 │
   + conversation_id    │                                             │
   + history (SQLite)   │   1. Query Analyzer   (rules-first, <1ms)   │
                        │        │  query_type, needs_context,        │
                        │        │  intent, complexity, confidence    │
                        │        ▼                                     │
                        │   2. Retrieval Router  (strategy selector)  │
                        │        ├── NEW_TASK      → no retrieval      │
                        │        ├── FOLLOWUP      → recent + affinity │
                        │        ├── MEMORY        → SQL structured    │
                        │        ├── SEMANTIC      → vector (KNN)      │
                        │        ├── COMPARISON    → multi-context     │
                        │        └── CORRECTION    → last interaction  │
                        │        ▼                                     │
                        │   3. Context Builder   (lean packet, budget)│
                        │        ▼                                     │
                        │   ContextPacket  (+ provider_affinity)      │
                        └────────────────────┬────────────────────────┘
                                             ▼
                        Routing Engine (UNCHANGED) → Provider (UNCHANGED)
```

**Integration point (unchanged signature):** both `ChatService.chat` ([chat_service.py](../app/services/chat_service.py#L51)) and `AutoRouter.route_and_chat` ([auto_router.py](../app/services/auto_router.py#L73)) already call:

```python
packet, engine_ms = self.memory.build_context(conversation_id, message, history)
```

The entire v2 engine lives behind this call. **No caller changes are required** for the retrieval fixes. (Provider affinity is the one optional, opt-in exception — see §8.)

---

## 2. Query Analyzer design

A hybrid classifier that mirrors the project's existing `HybridClassifier` philosophy (rules first, LLM only when uncertain) to stay well under the 100 ms budget. It analyzes **only the current prompt** (plus a couple of cheap history signals) — never the full history.

### Output contract

```python
class QueryType(str, Enum):
    NEW_TASK    = "new_task"
    FOLLOWUP    = "followup"
    MEMORY      = "memory"
    SEMANTIC    = "semantic"
    COMPARISON  = "comparison"
    CORRECTION  = "correction"

class RetrievalStrategy(str, Enum):
    NONE      = "none"
    RECENT    = "recent"
    SQL       = "sql"
    VECTOR    = "vector"
    MULTI     = "multi"        # comparison
    LAST_TURN = "last_turn"    # correction

@dataclass(frozen=True)
class QueryAnalysis:
    query_type: QueryType
    needs_context: bool
    strategy: RetrievalStrategy
    intent: str                # reuse existing intent vocabulary
    complexity: str            # "simple" | "moderate" | "complex"
    confidence: float          # 0..1
    signals: tuple[str, ...]   # matched rules, for explainability/logging
```

### Tier 1 — deterministic rules (<1 ms, resolves the vast majority)

Priority order matters (first match wins), because these categories overlap:

1. **MEMORY** (highest priority — structured, unambiguous):
   regex/anchors on *self-referential meta questions* — `what was my first/earliest (prompt|question|message)`, `what did i ask (earlier|before|first)`, `which provider (answered|replied|did you use)`, `how many (prompts|messages) (have i|did i) sent?`, `what did you say (earlier|before)`, `list my (prompts|questions)`. → `needs_context=True`, `strategy=SQL`.

2. **CORRECTION**: `no,? that('?s| is) wrong`, `that('?s| is) (incorrect|not right)`, `fix (the|your) (previous|last) (code|answer|solution)`, `that('?s)? broken`, leading `no,` / `nope` + negative. → `strategy=LAST_TURN`, affinity=strong.

3. **COMPARISON**: `compare (this|it|that) (with|to|against) (the )?(previous|last|earlier)`, `(vs|versus) (the )?(previous|last) (solution|answer|approach)`, `which is better`. → `strategy=MULTI`.

4. **FOLLOWUP** (reference to prior work, *regardless of leading verb* — this is the bug fix):
   - bare references: `continue`, `go on`, `again`, `keep going`, `more` (reuse `_PURE_REFERENCE`).
   - refinements: `explain (it|this|that|again|the solution|the code)`, `improve it`, `simplify it`, `why\??`, `optimize this`, `make it (shorter|better|faster)`, `fix this`.
   - **critical rule:** if the prompt contains a back-reference token (`again`, `it`, `this`, `that`, `the solution`, `the code`, `previous`, `last`, `above`) **or** is a short imperative refinement, it is a FOLLOWUP **even if it starts with "explain"/"what"**. This directly overrides the `_NEW_TOPIC_MARKERS` mis-fire. → `strategy=RECENT`, affinity=prefer.

5. **SEMANTIC** (a follow-up that introduces a *new but related* concept — "add authentication", "implement JWT", "create login"): a continuation verb + a **new content noun** not already dominant in the active thread. → `strategy=VECTOR` (falls back to lexical when embeddings are off).

6. **NEW_TASK** (default when nothing above matches): imperative build/ask with a fresh topic and **no** back-reference. → `needs_context=False`, `strategy=NONE`.

### Tier 2 — LLM fallback (gated, off the hot path by default)

Only invoked when Tier-1 confidence `< 0.7` **and** the config flag `context_llm_fallback_enabled` is on. Reuses the existing Ollama `qwen3:4b` via the same pattern as `IntentClassifier`, with a tiny JSON-mode prompt:

```
Classify the user's latest message into exactly one:
new_task | followup | memory | semantic | comparison | correction
Return JSON: {"query_type": "...", "needs_context": true/false, "confidence": 0..1}
```

Because Tier 1 already resolves every example in the spec with high confidence, the LLM path is a safety net, not a dependency. Default: **off**, so p99 latency is unaffected.

### Where this replaces existing logic
`QueryAnalyzer` **wraps** the existing `ContextAnalyzer` (it still provides keywords + follow-up markers) and adds the query-type decision on top. `ContextAnalyzer`, `ThreadManager`, `MemoryRetriever`, and `similarity.py` are **reused unchanged**; only the buggy "explain ⇒ new topic" *effect* is neutralised because the Query Analyzer now decides `needs_context`/`strategy` before thread assignment can skip retrieval.

---

## 3. Retrieval strategies

| Query type | Strategy | Retrieval method | Data source | What it returns |
|---|---|---|---|---|
| **New Task** | `NONE` | No retrieval | — | Empty context (`needs_context=False`) |
| **Follow-up** | `RECENT` | Recent-message retrieval within the active thread | `chat_messages` (thread window) | Last *k* user+assistant turns of the current thread (incl. the answer being referenced) + provider affinity |
| **Memory** | `SQL` | Structured deterministic query | `chat_messages` (indexed) | Exact fact(s): earliest user message, count, provider-of-answer, prior prompts list |
| **Semantic** | `VECTOR` | Embedding KNN, lexical fallback | `message_embeddings` (per-conversation) | Top-*k* semantically related prior turns across threads |
| **Comparison** | `MULTI` | Two-context retrieval | `chat_messages` (2 threads/solutions) | Current solution + the previous distinct solution |
| **Correction** | `LAST_TURN` | Last interaction retrieval | `chat_messages` (tail) | The immediately preceding user+assistant pair + strong provider affinity |

### 3.1 Recent (Follow-up)
`SELECT ... WHERE conversation_id=? AND thread_id=? ORDER BY id DESC LIMIT 2k`, re-ordered chronologically. **Always includes the last assistant answer** so "explain again" has the actual solution to re-explain. This is the fix for Examples 1 & 2.

### 3.2 SQL (Memory) — deterministic, ~1 ms
Concrete handlers, each keyed to a memory sub-intent detected by the analyzer:

```python
# "What was my first prompt?"  (excludes the current, not-yet-saved prompt)
SELECT content FROM chat_messages
WHERE conversation_id=? AND role='user' ORDER BY id ASC LIMIT 1;

# "How many prompts have I sent?"
SELECT COUNT(*) FROM chat_messages WHERE conversation_id=? AND role='user';

# "Which provider answered?" / "...answered X?"
SELECT provider, model FROM chat_messages
WHERE conversation_id=? AND role='assistant' ORDER BY id DESC LIMIT 1;

# "What did I ask earlier?"  (bounded list)
SELECT content FROM chat_messages
WHERE conversation_id=? AND role='user' ORDER BY id ASC LIMIT 10;
```

The result is placed into the context packet as a short **grounded fact block** (e.g., `Your first prompt was: "Build a REST API."`) so the selected provider answers correctly, without changing routing. This is the fix for Example 3. Note the current prompt is *not* in `history` at build time (it is saved only after the response — see `chat_service.py`), so "first prompt" never returns the question itself.

### 3.3 Vector (Semantic)
- **Scope:** the current conversation only (small N — typically tens to low-hundreds of turns). This makes brute-force cosine over cached vectors <5 ms with zero extension.
- Embed the **current prompt** once (hot path), compute cosine vs precomputed message vectors, take top-*k* above a floor. Falls back to `LexicalSimilarityScorer` if embeddings are unavailable.
- Implemented as an `EmbeddingScorer(SimilarityScorer)` — it satisfies the **existing protocol** ([similarity.py](../app/services/memory/similarity.py#L87)), so it drops into `MemoryRetriever`/`ThreadManager` with no interface change.

### 3.4 Multi (Comparison) & 3.5 Last-turn (Correction)
- Comparison: retrieve the active thread's most recent assistant solution **and** the previous distinct thread's solution (two anchors), so the model can actually compare.
- Correction: retrieve exactly the last `(user, assistant)` pair of the active thread; set strong provider affinity (fix the model's *own* output).

---

## 4. Context Builder

Reuses `ContextPacketBuilder`/`ContextPacket` with a few additive fields. Responsibilities:

1. **Assemble** only the strategy-selected turns (never full history — already the design).
2. **Token budget:** hard cap (default ~1,500 tokens of context). If exceeded:
   - keep the *anchor* (thread origin / referenced answer) and most-recent turns;
   - **smart-truncate** long assistant code blocks to `head + … + tail` rather than dropping them;
   - dedupe identical turns.
3. **Memory fact injection:** for `SQL` results, prepend a one-line grounded fact block.
4. **Chronological order** for a natural transcript.
5. **Attach provider affinity** (may be `None`).

Extended packet (backward compatible — all new fields defaulted):

```python
@dataclass
class ContextPacket:
    current_prompt: str
    context: list[ContextMessage]
    thread_id: str
    is_new_topic: bool
    total_history: int
    used_count: int
    reason: str = ""
    topic_keywords: list[str] = field(default_factory=list)
    # ── v2 additions (defaulted → existing ContextInfo mapping unaffected) ──
    query_type: str = "new_task"
    strategy: str = "none"
    provider_affinity: str | None = None   # ProviderId value or None
    memory_fact: str | None = None
```

`MemoryEngine.to_context_info` keeps mapping the existing fields; new fields are optional and can be surfaced to the UI later without breaking the current `ContextInfo`.

---

## 5. Required database changes (additive only)

All via the existing idempotent `Database._migrate` pattern ([database.py](../app/database/database.py#L82)) — nullable columns / new tables guarded by existence checks. **No column is dropped or renamed; no existing query breaks.**

```sql
-- Sidecar table (keeps the hot history() SELECT lean — vectors are read only on semantic queries)
CREATE TABLE IF NOT EXISTS message_embeddings (
    message_id INTEGER PRIMARY KEY REFERENCES chat_messages(id) ON DELETE CASCADE,
    model      TEXT NOT NULL,
    dim        INTEGER NOT NULL,
    vector     BLOB NOT NULL,          -- float32 bytes
    created_at TEXT NOT NULL
);

-- Optional analytics: store the classified query type per user message
ALTER TABLE chat_messages ADD COLUMN query_type TEXT;   -- nullable

-- Speeds up memory/SQL retrieval (first/earliest, per-role scans)
CREATE INDEX IF NOT EXISTS idx_chat_messages_conv_role
    ON chat_messages(conversation_id, role, id);
```

**Provider affinity needs no schema change** — `chat_messages.provider` / `.model` are already persisted per message.

---

## 6. Vector database recommendation

Prefer lightweight, local, minimal-infra options that align with the SQLite stack:

| Option | Fit | When to choose |
|---|---|---|
| **In-process numpy brute-force (recommended default)** | Vectors cached in the `message_embeddings` table; cosine in numpy, scoped per conversation. Zero new infra, <5 ms for hundreds of turns. | Per-conversation memory (the ThinkNRoute case). **Start here.** |
| **sqlite-vec** (extension) | KNN *inside* the existing SQLite file — one DB, one connection, no server. | If/when you need cross-conversation or global long-term memory at scale. |
| **Chroma** (embedded persistent) | Batteries-included local vector store, higher-level API. | If you want a managed collection API and metadata filtering without SQL. |

**Recommendation:** ship with **numpy brute-force over the sidecar table** (no dependency, meets latency), and keep `sqlite-vec` as the documented upgrade path when global memory is added. This honors "prefer lightweight local solutions" and avoids standing up a vector server.

---

## 7. Embedding model recommendation

Lightweight, local, and ideally reusing infrastructure already present (Ollama):

| Model | Dim | Runtime | Notes |
|---|---|---|---|
| **`nomic-embed-text` via Ollama (recommended)** | 768 | Existing Ollama (`settings.ollama_base_url`) | Zero new Python deps; reuses the running Ollama. ~10–30 ms/prompt CPU. |
| `bge-small-en-v1.5` / `all-MiniLM-L6-v2` via **fastembed** | 384 | ONNX, in-process CPU | ~120 MB, no torch, ~5–15 ms/prompt. Use if you don't want retrieval to depend on Ollama being up. |

**Latency plan (keeps <100 ms):**
- **Write-time:** embed each new user+assistant message *after* the response is returned (FastAPI `BackgroundTasks` / `asyncio.create_task`) and store in `message_embeddings`. Never blocks the reply.
- **Read-time (hot path):** embed **only the current prompt** (one short call), then brute-force cosine over cached vectors. A single embedding + cosine over ≤ a few hundred vectors is comfortably within budget. If the embedder times out (hard cap, e.g., 60 ms), the retriever transparently falls back to lexical — the request never stalls.

---

## 8. FastAPI integration

**No new endpoints and no router/provider changes are required for the retrieval fixes.** The engine is entered through the unchanged `build_context` call in both modes.

Two optional, additive hooks:

1. **Write-time embedding (background):** after `storage.save_message(...)` in `ChatService.chat` and `AutoRouter.route_and_chat`, schedule embedding via `BackgroundTasks` (or `asyncio.create_task`). Fire-and-forget; failures are logged, not raised.

2. **Provider affinity (opt-in, `provider_affinity_enabled`, default configurable):**
   - `build_context` returns `packet.provider_affinity` for `FOLLOWUP`/`CORRECTION`.
   - **Manual mode:** affinity is informational (the user chose the provider) — surfaced in `ContextInfo`, no behavior change.
   - **Auto mode:** in `AutoRouter`, when affinity is set and that provider is connected/healthy, **re-order the existing failover chain** to try the affinity provider first. The **RoutingEngine is untouched** — we only reorder candidates the engine already produced, and only for follow-up/correction turns.

   > ⚠️ **Explicit trade-off:** the spec says both "don't change routing logic" *and* "prefer the same provider for follow-ups." These are in tension. The proposal resolves it by keeping `RoutingEngine.route()` byte-for-byte identical and applying affinity as an **optional, flag-gated re-ordering inside `AutoRouter`** (the orchestrator), never inside the routing engine. Default the flag however you prefer; with it off, routing is exactly as today.

---

## 9. New modules / files to create

All inside the existing `app/services/memory/` package (extending the seam, not replacing it):

```
app/services/memory/
├── query_analyzer.py         # NEW — QueryType, RetrievalStrategy, QueryAnalysis, rules (Tier 1)
├── llm_query_analyzer.py     # NEW — optional Tier-2 Ollama fallback (gated)
├── retrieval_router.py       # NEW — QueryAnalysis → strategy → retriever; returns turns + affinity
├── retrievers/
│   ├── __init__.py
│   ├── recent_retriever.py   # NEW — follow-up: recent thread window
│   ├── memory_sql_retriever.py  # NEW — memory: structured SQL facts
│   ├── semantic_retriever.py # NEW — semantic: vector KNN + lexical fallback
│   ├── comparison_retriever.py  # NEW — comparison: two-context
│   └── correction_retriever.py  # NEW — correction: last interaction
├── embeddings.py             # NEW — EmbeddingProvider (Ollama/fastembed), EmbeddingScorer(SimilarityScorer)
├── embedding_store.py        # NEW — read/write message_embeddings, background embed
├── provider_affinity.py      # NEW — resolve affinity provider for a thread
│
├── memory_engine.py          # EDIT — wire analyzer → router → builder (thin change)
├── context_packet_builder.py # EDIT — additive packet fields + budget/truncation
│
├── context_analyzer.py       # REUSED (unchanged)
├── thread_manager.py         # REUSED (unchanged)
├── memory_retriever.py       # REUSED (lexical scorer for recent/semantic fallback)
├── similarity.py             # REUSED (EmbeddingScorer implements this protocol)
├── context_cache.py          # REUSED (LRU)
└── thread_manager.py
```

Config additions in `app/config.py` (all defaulted, non-breaking): `context_engine_v2`, `semantic_retrieval_enabled`, `context_llm_fallback_enabled`, `provider_affinity_enabled`, `embedding_model`, `context_token_budget`.

---

## 10. Folder structure (delta view)

Only the memory package grows; everything else is untouched:

```
backend/app/
├── api/               # UNCHANGED (chat.py, models.py, providers.py)
├── database/          # database.py: +1 additive migration block
├── models/            # schemas.py: optional additive ContextInfo fields (later)
├── providers/         # UNCHANGED
├── services/
│   ├── auto_router.py     # +optional affinity re-order (flag-gated)
│   ├── chat_service.py    # +optional background embed hook
│   ├── routing_engine.py  # UNCHANGED (guaranteed)
│   ├── hybrid_classifier.py / intent_classifier.py / rule_classifier.py  # REUSED
│   └── memory/            # ← all new modules land here (see §9)
└── main.py                # wiring only: pass config/embedder into MemoryEngine
```

---

## 11. Step-by-step implementation plan (phased, each phase ships independently)

**Phase 0 — Query Analyzer + wiring (fixes Examples 1–3, no vectors)**
1. Add `query_analyzer.py` (Tier-1 rules) + unit tests for the six types and the three failing examples.
2. Add `retrieval_router.py`, `recent_retriever.py`, `memory_sql_retriever.py`, `correction_retriever.py`, `comparison_retriever.py`.
3. Edit `memory_engine.py`: run analyzer → route → build. Keep lexical retrieval as the semantic fallback.
4. Ship behind `context_engine_v2` flag (default on after tests) → **Examples 1, 2, 3 now pass.**

**Phase 1 — Context Builder hardening**
5. Token budget + smart code truncation + memory fact injection in `context_packet_builder.py`.

**Phase 2 — Semantic (vectors)**
6. Add `embeddings.py` (`OllamaEmbedder` + `EmbeddingScorer`), `embedding_store.py`, `message_embeddings` migration.
7. Background embed-at-write hook; brute-force numpy KNN in `semantic_retriever.py`; flag `semantic_retrieval_enabled` (lexical fallback always available).

**Phase 3 — Provider affinity (opt-in)**
8. `provider_affinity.py`; surface in `ContextInfo`; flag-gated re-order in `AutoRouter`.

**Phase 4 — Optional scale & analytics**
9. `sqlite-vec` upgrade path; `query_type` analytics column; optional Tier-2 LLM fallback.

Every phase: feature-flagged, unit-tested, with lexical fallback preserved.

---

## 12. Migration strategy (zero breakage)

- **DB:** additive migrations only, via the proven `_migrate` idempotent pattern. Existing rows stay valid (new columns nullable; embeddings backfilled lazily).
- **API/contract:** `build_context` signature and return type unchanged; `ContextPacket`/`ContextInfo` extended with **defaulted** fields → existing serialization and the frontend are unaffected.
- **Backfill:** embeddings computed on write going forward; missing vectors (legacy messages) → semantic retriever falls back to lexical for those turns. No batch job required (optional one-off script provided if desired).
- **Feature flags:** default to safe values; `context_engine_v2=off` reproduces today's behavior exactly.
- **Rollback:** flip flags off → instant revert to the current lexical engine, no redeploy of routing/providers.
- **Guaranteed untouched:** `routing_engine.py`, all `providers/*`, `api/*`, DB schema semantics, and the frontend.

---

## 13. Edge cases & handling

| Edge case | Handling |
|---|---|
| Empty history / first message | `NEW_TASK`, `needs_context=False` (already handled in `build_context`). |
| "continue" as the *first* message | No active thread → return empty context gracefully, never error. |
| "What was my first prompt?" when it *is* the first prompt | SQL returns nothing → grounded fact "this is your first message." |
| Memory query self-match (Example 3) | Structured SQL bypasses lexical entirely; current prompt isn't in `history` yet, so it can't be returned. |
| Ambiguous memory ("what did I ask earlier") | Bounded list (LIMIT 10), chronological. |
| Follow-up starting with "explain"/"what" | Back-reference rule forces `FOLLOWUP` over `_NEW_TOPIC_MARKERS` — the core bug fix. |
| Very long conversations | Recent/SQL windows are bounded; vector search scoped per-conversation; token budget caps the packet. |
| Token explosion from large code answers | Smart head+tail truncation, dedupe, hard budget. |
| Non-English / paraphrase | Embeddings outperform lexical; lexical remains as fallback. |
| Embedder/Ollama down or slow | Hard timeout → transparent fallback to `LexicalSimilarityScorer`; request never stalls (<100 ms preserved). |
| Analyzer uncertain | Default to a **safe** strategy (`RECENT`) rather than `NONE`, erring toward continuity; optional LLM tie-breaker if enabled. |
| Provider affinity provider disconnected/failing | Affinity is a *preference* — falls back to the normal failover chain; never blocks a response. |
| Concurrency (shared caches) | LRU thread-view cache is keyed by `(conversation_id, len(history))`; additive, safe. |

---

## Appendix — how the three failing examples flow in v2

```
"Explain the solution again"
  Analyzer: back-reference ("again", "the solution") ⇒ FOLLOWUP, needs_context=True, strategy=RECENT
  Router  : recent window of active (software) thread, incl. last assistant code answer
  Builder : [user: Build a REST API] [assistant: <code>] + current prompt
  Result  : provider re-explains the actual prior solution ✓  (+ affinity: same provider)

"What was my first prompt?"
  Analyzer: memory meta-question ⇒ MEMORY, strategy=SQL
  Router  : SELECT content ... role='user' ORDER BY id ASC LIMIT 1  → "Build a REST API."
  Builder : fact block 'Your first prompt was: "Build a REST API."'
  Result  : provider answers correctly with the earliest message ✓

"Add authentication"  (after a website task)
  Analyzer: continuation verb + new concept ⇒ SEMANTIC, strategy=VECTOR (lexical fallback)
  Router  : top-k related prior turns (the website/build thread)
  Result  : provider extends the existing project with auth ✓
```
