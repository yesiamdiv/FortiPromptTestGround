# Memory: Plugin & Extension Patterns

## Where new modules belong

| What you're adding | Where it goes |
|---|---|
| New attacker powered by an LLM | `src/attackers/llm_attacker.py` (reuse) or new file |
| New attacker reading from a file/DB | New file in `src/attackers/` |
| New attack strategy (how to craft prompts) | New file in `src/attackers/strategies/` |
| New defender wrapping an external API | `src/defenders/api_defender.py` (reuse) or new file |
| New defender using a LangChain model | `src/defenders/llm_defender.py` (reuse) or new file |
| New input guard (blocks bad prompts) | New file in `src/defenders/filters/`, use as `pre_filter` |
| New output guard (blocks data leakage) | New file in `src/defenders/filters/`, use as `post_filter` |
| New evaluator using an LLM | New file in `src/evaluators/` |
| New evaluator using rules/regex | New file in `src/evaluators/` |

## The interface contract

Every plugin implements exactly one abstract base from `src/core/interfaces.py`:
- Attacker → `BaseAttacker.generate_attack(state) -> dict`
- Defender → `BaseDefender.get_response(state) -> dict`  
- Evaluator → `BaseEvaluator.evaluate(state) -> dict`
- Strategy → `BaseAttackStrategy.build_prompt(state) -> str`
- Filter → `BaseFilter.check(text) -> FilterResult`

## LLM models are always injected

Never instantiate `ChatOpenAI`, `ChatAnthropic`, etc. inside a module. Always accept a `BaseChatModel` parameter and let the caller (`main.py`) decide the provider. This keeps every module provider-agnostic.

## Wiring happens only in main.py

`main.py` is the only place where concrete implementations are imported and composed together. The core modules (`orchestrator.py`, `interfaces.py`) only ever import abstract base classes.
