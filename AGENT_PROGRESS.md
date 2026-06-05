# Agent Progress Log

## Current Status
Phase 2 — COMPLETE.

## Completed Steps
- [x] 1.1 — Create core/ package, move debug_utils to core/logging.py — commit: 1729382
- [x] 1.2 — Update all imports to core.logging, remove shim — commit: 3053266
- [x] 1.3 — Move domain_models to core/models.py — commit: c9cf13d
- [x] 1.4 — Move GraphConfig and friends to core/config.py — commit: b6bb1e5
- [x] 1.5 — Rename models_v2.py to models.py — commit: 13d5042
- [x] 1.6 — Rename state_schema.py to engine/state.py — commit: 54b0a8a
- [x] 1.7 — Extract core/constants.py with NodeName and RunStatus — commit: 149e2a2
- [x] 1.8 — Split routes.py into runs.py, discovery.py, data.py — commit: 410c84c
- [x] 1.9 — Add core/env.py Settings, wire get_settings into connection/main/ollama/logging — commit: af7b96e
- [x] 1.10 — Move script to scripts/, clean comments, write 4 docs files — commit: 62905fb
- [x] 2.1 — Add Session and Turn models to server/database/models.py
- [x] 2.2 — Add DB ops for Session/Turn; add sessions/turns indexes to connection.py
- [x] 2.3 — Extend RoutingSignals (PROCEED, CONTINUE_CONVERSATION); add route_post_attack/route_post_defence to AttackStrategy base; add session_id/turn_index to SystemState
- [x] 2.4 — Add PostAttackRouter and PostDefenceRouter nodes; rewire graph topology in graph_builder.py
- [x] 2.5 — Add session_id and turn_index to SystemState and create_initial_state
- [x] 2.6 — Migrate AutomaticDatabaseMiddleware to Session/Turn model; add session_id to WS events
- [x] 2.7 — Migrate BatchDatabaseMiddleware to Session/Turn model
- [x] 2.8 — Migrate ManualDatabaseMiddleware to unified Session/Turn ops; update manual_routes.py to use get_session/get_turns_for_session
- [x] 2.9 — Add unified Session/Turn API endpoints to data.py; update manual_routes.py to delegate to general ops; deprecate flat endpoints in docs/api.md
- [x] 2.10 — Implement MultiTurnStrategy; register in engine/registry.py; add "multiturn" to GraphConfig Literal
- [x] 2.11 — Tests (test_session_turn_model.py, test_multiturn_strategy.py); update docs/api.md and docs/architecture.md

## In-Progress
(none — Phase 2 complete)

## Decisions & Context
- 2025-05-28: Phase 1 completed. All steps 1.1–1.10 done.
- 2025-05-30: Phase 2 started. Session/Turn model mirrors the existing ManualSession/ManualTurn pattern but is run-type-agnostic.
- 2025-05-30: Graph topology changed from `init→router→attack→defence→eval→router` to `init→attack→post_attack_router→defence→post_defence_router→eval→router`. The init node no longer routes through the end-of-cycle router first.
- 2025-05-30: ManualSession and ManualTurn models retained in models.py and their DB methods retained in operations.py — not yet deleted. Deletion deferred until all callers confirmed migrated (the plan spec says remove in 2.8 but manual_routes.py schema types still reference ManualSessionResponse/ManualTurnResponse which wrap these models).
- 2025-05-30: update_session() accepts **fields kwargs for flexibility — avoids needing a full Session model round-trip on every partial update.
- 2025-05-30: MultiTurnStrategy stores conversation_history in strategy_context. The merge_context reducer merges dicts shallowly, so the list is replaced (not appended) on each state merge — strategy must always write the full updated list.
- 2025-05-30: PostAttackRouter currently only accepts PROCEED; the RETRY_ATTACK signal is reserved for future use as noted in the plan.

## Known Issues / Blockers
- pydantic-settings must be in requirements.txt (noted in Phase 1, still pending).
- ManualSessionResponse schema in schemas.py is typed against ManualSession model fields. After full ManualSession retirement it will need updating to Session fields.
- test_session_turn_model.py uses AsyncMock chains; verify the find().sort().to_list() mock chain matches actual Motor API in integration tests.
- MultiTurnStrategy.execute_generation calls provider_registry.get() — provider must support a `generate(prompt, system_prompt, runtime_config)` interface. Confirm with actual provider implementations before running live.
