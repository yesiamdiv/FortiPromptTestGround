# Memory: State & Data Flow

## The ArenaState is the only communication channel

No node ever calls another node directly. All data exchange happens through `ArenaState` in `src/core/state.py`.

## Partial returns are intentional

Nodes return only the keys they changed. LangGraph merges the partial dict back into the full state. This is correct behaviour — do not refactor nodes to return the full state.

## History is append-only inside the orchestrator

The Orchestrator's attacker and defender node wrappers automatically append to `chat_history` after each node runs. Individual nodes should NOT append to history themselves unless they have a specific reason to manage it (e.g. the `should_reset_history` pattern in strategies).

## strategy_metadata is the attacker's scratchpad

The attacker can write anything into `strategy_metadata` between turns — failed attempt summaries, pivot hints, approach notes. The Orchestrator never reads or modifies this field. It's purely for the attacker's internal continuity across the loop.

## turn_count is incremented by the orchestrator wrapper, not the attacker

The attacker node wrapper in `orchestrator.py` handles `turn_count += 1`. Attacker modules should not increment it themselves.
