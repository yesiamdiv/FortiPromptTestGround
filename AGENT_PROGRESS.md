# Agent Progress Log

## Current Status
Phase 1 — COMPLETE. Ready for Phase 2.

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

## In-Progress
(none — Phase 1 complete)

## Decisions & Context
- 2025-05-28: Session started fresh. No prior progress file.
- 2025-05-28: core/logging.py PROJECT_ROOT uses parents[1] (core/ is one level from root), matching original engine/ depth.
- 2025-05-28: core/logging.py loads DEBUG_ENABLED and MIN_LOG_LEVEL lazily from get_settings() to avoid circular imports at module load time.
- 2025-05-28: run_manager.py RunStatus is a str+Enum (used for type-safe comparisons); core/constants.py RunStatus is plain strings (used where enum overhead isn't needed). Both coexist intentionally.
- 2025-05-28: discovery.py absorbs all of discovery_routes.py endpoints (under /discovery/ prefix) plus the strategy/provider/node listing from the old routes.py. No endpoint paths changed.
- 2025-05-28: nodes/data/multilayer defence/ model binaries (.joblib, .pkl, etc.) were removed with the script since they are build artifacts. The fortiprompt_harmful_detector directory was retained in nodes/data/ as it is loaded at runtime by multilayer_defense_node.py.

## Known Issues / Blockers
- pydantic-settings must be installed for core/env.py (pip install pydantic-settings). Not in requirements.txt yet — add before Phase 2.
- nodes/data/fortiprompt_harmful_detector was left in nodes/data/ (runtime model artifact, not a script). No action needed.
