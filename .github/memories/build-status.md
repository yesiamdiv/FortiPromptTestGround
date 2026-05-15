# Memory: Build Status & What's Next

## Completed

- `src/core/state.py` — ArenaState TypedDict
- `src/core/interfaces.py` — all abstract base classes
- `src/core/orchestrator.py` — full LangGraph graph with conditional routing and telemetry node
- `src/attackers/llm_attacker.py` — LangChain-powered attacker
- `src/attackers/mock_attacker.py` — JSON dataset attacker
- `src/attackers/strategies/single_turn.py` — stateless one-shot strategy
- `src/attackers/strategies/multi_turn.py` — history-aware escalation strategy
- `src/defenders/api_defender.py` — raw HTTP POST to external endpoint
- `src/defenders/mock_defender.py` — scripted responses for testing
- `src/defenders/langchain_defender.py` — LangChain model as defender (needs rename to llm_defender.py)
- `src/defenders/filters/base_filter.py` — BaseFilter + FilterResult
- `src/evaluators/llm_judge.py` — LLM-as-judge with structured BREACHED/BLOCKED output
- `src/evaluators/string_judge.py` — deterministic regex/substring judge
- `src/telemetry/tracker.py` — SQLiteTracker
- `main.py` — example wiring with mocks

## In Progress / Incomplete

### `src/core/` bugs and gaps
- [ ] `orchestrator.py` — `final_outcome` can be `"ongoing"` in the returned state. Needs finalisation step before `run()` returns to guarantee it's always `"attacker_wins"` or `"defender_wins"`.
- [ ] `orchestrator.py` — `setup()` calls need to be idempotent or guarded. Currently, they run on every `run()` call, which can be problematic for batch processing.
- [ ] `orchestrator.py` — Node factories lack robust error handling. Unhandled exceptions can crash the graph without telemetry.
- [ ] `state.py` — Add `run_config: dict` field for passing arbitrary per-run settings to plugins without polluting top-level fields.
- [ ] `interfaces.py` — Evaluate if `BaseAttackStrategy` belongs in `src/core/` or should be moved to `src/attackers/` as it's only used by `LLMAttacker`.

### `src/defenders/` missing files
- [ ] `src/defenders/filters/regex_pre_filter.py` — started, cut off mid-file, needs to be completed
- [ ] `src/defenders/llm_defender.py` — not yet created; should accept `pre_filters: list[BaseFilter]` and `post_filters: list[BaseFilter]`, run them around the LLM call, and short-circuit if any filter fires
- [ ] `src/defenders/langchain_defender.py` — rename/replace with `llm_defender.py` for consistency with `llm_attacker.py`

## Planned (not started)

- `src/defenders/filters/semantic_filter.py` — embedding similarity check against a blocklist of forbidden topics
- `src/defenders/filters/pii_filter.py` — post-filter that catches outgoing sensitive data (names, keys, secrets)
- `src/attackers/strategies/roleplay.py` — persona/fictional framing strategy
- `src/attackers/strategies/encoded.py` — base64 / rot13 obfuscation strategy
- `cli.py` — terminal runner with flags so runs don't require editing `main.py`
- Batch runner — loops `orchestrator.run()` over a full dataset and aggregates breach rates per strategy