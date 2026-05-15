# Memory: Decisions & Hard Rules

## Hard rules — never violate these

- **Never let the Orchestrator import a concrete attacker, defender, or evaluator class.** It only imports `BaseAttacker`, `BaseDefender`, `BaseEvaluator` interfaces. Concrete classes belong in `main.py`.
- **Never hardcode an LLM provider inside a module.** Always inject via constructor parameter typed as `BaseChatModel`.
- **Never add memory/state management to the Orchestrator.** It passes state through — it does not store, summarise, or transform it.
- **Never let nodes communicate directly with each other.** They only read/write the shared state dict.
- **Filters are internal to defenders.** They are not nodes in the graph, not evaluators, and the Orchestrator knows nothing about them.
- **Evaluation result must always be exactly `"breached"`, `"blocked"`, or `"error"`** (lowercase strings). The router does a string comparison on this value. Any other value will cause the graph to behave unexpectedly.

## Design decisions already made

- **LangGraph over a manual loop**: chosen because it handles state merging, conditional routing, and future async/parallel execution cleanly.
- **SQLite over a file log**: structured queries over runs are more useful than reading raw JSON logs.
- **Strategies injected into LLMAttacker, not subclassed**: keeps the LLM-calling code DRY. Only the prompt construction logic changes between strategies.
- **Filters injected into LLMDefender as lists**: allows stacking multiple filters without subclassing. Order matters — they run sequentially, first match wins.
- **Judge uses a separate LLM from the attacker**: reduces evaluation bias. The judge should ideally be a stronger or different model from the one doing the attacking.
