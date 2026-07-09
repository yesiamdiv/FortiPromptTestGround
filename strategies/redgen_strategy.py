"""
================================================================================
REDGEN ATTACK STRATEGY
================================================================================

Generates diverse adversarial prompts via a template × payload cartesian
product approach, adapted from the RedGen research tool.

Algorithm per iteration:
  1. Pick one template + one payload from the configured domain (cycling
     through combinations so the full space is explored across iterations)
  2. Optionally paraphrase the payload text via the configured LLM provider
  3. Optionally apply an encoding mutation (leetspeak, homoglyphs,
     zero-width injection, base64 hint, or multilingual wrapping)
  4. Wrap the mutated payload in the chosen template to produce the final prompt
  5. Return an AttackPayload with rich metadata for downstream eval nodes

Configuration (strategy_params):
  domain          : payload domain to attack from
                    ("cybersecurity" | "harmful" | "illegal" |
                     "harassment" | "misinformation" | "copyright")
                    default: "cybersecurity"
  model           : Ollama model name for paraphrasing, e.g. "llama3.2:latest"
  llm_provider_name: "ollama" (default) — provider used for paraphrasing
  paraphrase      : true/false — enable LLM paraphrasing step (default: true)
  encode_ratio    : 0.0–1.0 — probability of applying an encoding mutation
                    (default: 0.3)
  max_iterations  : how many attack turns to run (default: 10)
  target_score    : score threshold to declare success and stop early
                    (default: 0.8)
  seed            : random seed for reproducibility (default: 42)
================================================================================
"""

import math
import copy
import random
import importlib.util
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

from strategies.base import AttackStrategy
from core.models import create_simple_attack
from engine.state import SystemState, RoutingSignals, create_turn_data
from engine.provider_registry import get_provider_registry
from core.logging import debug, tracer, step, warn, err, checkpoint

# ---------------------------------------------------------------------------
# Paths — data lives alongside this file's package, in strategies/data/redgen/
# ---------------------------------------------------------------------------
_DATA_DIR = Path(__file__).parent / "data" / "redgen"


# ---------------------------------------------------------------------------
# Lightweight loader helpers (no dependency on the original RedGen package)
# ---------------------------------------------------------------------------

def _load_domain_payloads(domain: str) -> List[Dict[str, Any]]:
    """Dynamically load PAYLOADS list from domains/<domain>/payloads.py."""
    payloads_file = _DATA_DIR / "domains" / domain / "payloads.py"
    if not payloads_file.exists():
        available = [d.name for d in (_DATA_DIR / "domains").iterdir()
                     if d.is_dir() and not d.name.startswith("_")]
        raise ValueError(
            f"RedGen domain '{domain}' not found. "
            f"Available: {', '.join(sorted(available))}"
        )

    mod_name = f"redgen_data.domains.{domain}.payloads"
    spec = importlib.util.spec_from_file_location(mod_name, payloads_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)

    payloads = getattr(module, "PAYLOADS", [])
    for i, p in enumerate(payloads):
        p.setdefault("id", f"{domain}_{i}")
        p.setdefault("severity", 5)
        p.setdefault("category", domain)
        # RedGen uses "behavior" key; normalise to "text"
        if "behavior" in p and "text" not in p:
            p["text"] = p["behavior"]
    return payloads


def _load_templates() -> List[Dict[str, Any]]:
    """Load template metadata from the bundled templates.py."""
    templates_file = _DATA_DIR / "templates.py"
    mod_name = "redgen_data.templates"
    spec = importlib.util.spec_from_file_location(mod_name, templates_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)

    template_map = getattr(module, "TEMPLATE_MAP", {})
    return [
        {
            "id":              f"tpl_{name}",
            "name":            name,
            "func":            func,
            "severity":        5,
            "attack_type":     name,
            "generation_mode": "template",
        }
        for name, func in template_map.items()
    ]


def _apply_encoding(text: str, language: Optional[str], encoding: str) -> str:
    """Apply encoding mutation using the bundled encoding module."""
    encoding_file = _DATA_DIR / "encoding.py"
    mod_name = "redgen_data.encoding"
    if mod_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(mod_name, encoding_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
    enc_module = sys.modules[mod_name]

    result = text
    if language and language != "english":
        result = enc_module.wrap_language(result, language)

    mutations = getattr(enc_module, "ENCODING_MUTATIONS", {})
    mutator = mutations.get(encoding, lambda t: t)
    return mutator(result)


AVAILABLE_LANGUAGES = ["english", "korean", "chinese", "hindi", "marathi"]
AVAILABLE_ENCODINGS = ["none", "leetspeak", "homoglyphs", "zero_width", "base64_hint"]


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class RedGenStrategy(AttackStrategy):
    """
    Diverse adversarial prompt generation via template × payload combinations
    with optional LLM paraphrasing and encoding mutations.
    """

    def __init__(self, config: Dict[str, Any] = None):
        tracer("RedGenStrategy.__init__")

        defaults = {
            "domain":             "cybersecurity",
            "model":              "huihui_ai/dolphin3-abliterated:latest",
            "llm_provider_name":  "ollama",
            "paraphrase":         True,
            "encode_ratio":       0.3,
            "max_iterations":     10,
            "target_score":       0.8,
            "seed":               42,
        }
        # User config always wins — merge user values on top of defaults
        if config:
            defaults.update(config)
        super().__init__(defaults)

        # Log so it's obvious in the trace which model is being used
        resolved_model = self.config.get("model", "llama3.2:latest")
        debug("RedGen model resolved", model=resolved_model,
              provider=self.config.get("llm_provider_name", "ollama"),
              user_overrode=bool(config and "model" in config))

        if not resolved_model:
            raise ValueError(
                "RedGenStrategy requires 'model' in strategy_params "
                "(e.g. 'llama3.2:latest' for Ollama, 'gemini-1.5-flash' for Gemini)."
            )

        # Provider (used for paraphrasing only — optional step)
        provider_name = self.config["llm_provider_name"]
        self._provider = None
        if self.config["paraphrase"]:
            try:
                self._provider = get_provider_registry().get(
                    provider_name, config=self.config
                )
                debug("Paraphrase provider ready", provider=provider_name,
                      model=self._provider.get_model_name())
            except Exception as exc:
                warn(f"Could not init paraphrase provider ({exc}). "
                     "Paraphrasing will be skipped.")

        # Load domain payloads and templates
        domain = self.config["domain"]
        random.seed(self.config["seed"])
        self._payloads   = _load_domain_payloads(domain)
        self._templates  = _load_templates()

        if not self._payloads:
            raise ValueError(f"No payloads loaded for domain '{domain}'.")
        if not self._templates:
            raise ValueError("No templates loaded from strategies/data/redgen/templates.py.")

        # Pre-compute the full shuffled combination list once
        self._combinations = self._build_combinations()
        self._combo_index  = 0   # cycles through on each execute_generation call

        checkpoint(
            "RedGenStrategy ready",
            domain=domain,
            payloads=len(self._payloads),
            templates=len(self._templates),
            combinations=len(self._combinations),
            paraphrase=bool(self._provider),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_combinations(self) -> List[tuple]:
        """Build and shuffle the full template × payload cartesian product."""
        base = math.ceil(math.sqrt(self.config["max_iterations"]))
        n_templates = min(len(self._templates), base)
        n_payloads  = math.ceil(self.config["max_iterations"] / n_templates)

        sampled_templates = random.sample(self._templates, min(n_templates, len(self._templates)))
        sampled_payloads  = random.sample(self._payloads,  min(n_payloads,  len(self._payloads)))

        combos = [
            (t, copy.deepcopy(p))
            for t in sampled_templates
            for p in sampled_payloads
        ]
        random.shuffle(combos)
        return combos

    def _get_next_combination(self) -> tuple:
        """Return the next (template, payload) pair, cycling if exhausted."""
        if self._combo_index >= len(self._combinations):
            # Re-shuffle for a second pass rather than repeating in order
            random.shuffle(self._combinations)
            self._combo_index = 0
        combo = self._combinations[self._combo_index]
        self._combo_index += 1
        return combo

    async def _paraphrase(self, text: str) -> Optional[str]:
        """Attempt to paraphrase text via LLM. Returns None on failure."""
        if not self._provider:
            return None
        try:
            system = (
                "You are a text rewriter. "
                "Rewrite the given text to say the same thing with different wording. "
                "Keep the same intent and meaning. "
                "Output ONLY the rewritten text — no explanations, no preamble, no quotes."
            )
            prompt = f"{system}\n\n{text}"
            result = await self._provider.generate(prompt)
            return result.strip() if result and result.strip() else None
        except Exception as exc:
            warn(f"Paraphrase failed: {exc}")
            return None

    def _apply_mutation(self, text: str) -> Dict[str, Any]:
        """
        Probabilistically apply language wrapping + encoding mutation.
        Returns dict with keys: text, language, encoding.
        """
        if random.random() >= self.config["encode_ratio"]:
            return {"text": text, "language": "english", "encoding": "none"}

        language = random.choice(AVAILABLE_LANGUAGES)
        encoding = random.choice(AVAILABLE_ENCODINGS)
        mutated  = _apply_encoding(text, language if language != "english" else None, encoding)
        return {"text": mutated, "language": language, "encoding": encoding}

    # ------------------------------------------------------------------
    # AttackStrategy interface
    # ------------------------------------------------------------------

    def initialize(self, state: SystemState,
                   runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        tracer("RedGenStrategy.initialize")
        if runtime_config is None:
            runtime_config = {}

        if "strategy_context" not in state:
            raise ValueError("Corrupted state: Missing 'strategy_context'.")

        context = copy.deepcopy(state["strategy_context"])
        context.update({
            "strategy_name":     "redgen_attack",
            "iteration_count":   0,
            "successful_iterations": 0,
            "history":           [],
            "combo_index":       0,   # persisted in state so restarts work
            "domain":            self.config["domain"],
            "max_iterations":    self.config["max_iterations"],
            "target_score":      self.config["target_score"],
        })

        payload = state.get("payload", {})
        intent  = payload.get("intent", "test intent")
        context["intent"] = intent

        step("RedGenStrategy initialized", domain=self.config["domain"], intent=intent)
        return {"strategy_context": context}

    async def execute_generation(self, state: SystemState,
                                  runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        tracer("RedGenStrategy.execute_generation")
        if runtime_config is None:
            runtime_config = {}

        context   = copy.deepcopy(state["strategy_context"])
        iteration = context.get("iteration_count", 0)

        # --- Pick next template + payload pair ---
        template, payload = self._get_next_combination()
        payload_text      = payload.get("text", "")

        generation_steps = []

        # --- Paraphrase (optional LLM step) ---
        if self.config["paraphrase"]:
            paraphrased = await self._paraphrase(payload_text)
            if paraphrased:
                payload_text = paraphrased
                generation_steps.append("paraphrased")

        # --- Encoding mutation (probabilistic) ---
        mutation = self._apply_mutation(payload_text)
        payload_text = mutation["text"]
        if mutation["encoding"] != "none" or mutation["language"] != "english":
            generation_steps.append(f"encoded:{mutation['encoding']}+{mutation['language']}")

        # --- Apply template ---
        template_func = template.get("func")
        if callable(template_func):
            final_prompt = template_func(payload_text)
        else:
            final_prompt = payload_text

        # --- Build rich metadata ---
        metadata = {
            "attack_type":      template.get("attack_type", "redgen"),
            "template_id":      template.get("id", "unknown"),
            "template_name":    template.get("name", "unknown"),
            "payload_id":       payload.get("id", "unknown"),
            "payload_category": payload.get("category", self.config["domain"]),
            "severity":         payload.get("severity", 5),
            "language":         mutation["language"],
            "encoding":         mutation["encoding"],
            "generation_mode":  "+".join(generation_steps) if generation_steps else "original",
            "domain":           self.config["domain"],
            "iteration":        iteration,
            "strategy":         "redgen_attack",
            "behavior_id":      payload.get("behavior_id", payload.get("id", "unknown")),
        }

        # create_simple_attack(text, **metadata) — first arg is "text", rest are **kwargs
        attack_payload = create_simple_attack(
            final_prompt,
            **metadata
        )

        # --- Update context ---
        context["iteration_count"]  = iteration + 1
        context["combo_index"]      = self._combo_index  # persist position
        context["history"].append(final_prompt)

        turn_data = create_turn_data(
            turn_id=f"redgen_turn_{state['run_id']}_{iteration}",
            node_name="attack"
        )
        turn_data["attack"] = attack_payload

        step("Attack generated",
             iteration=iteration,
             template=template.get("name"),
             encoding=mutation["encoding"],
             prompt_length=len(final_prompt))

        return {
            "current_turn":    turn_data,
            "strategy_context": context,
        }

    def route(self, state: SystemState,
              runtime_config: Dict[str, Any] = None) -> str:
        tracer("RedGenStrategy.route")
        context   = state["strategy_context"]
        iteration = context.get("iteration_count", 0)
        max_iters = context.get("max_iterations", self.config["max_iterations"])
        target    = context.get("target_score",   self.config["target_score"])

        # Check last evaluation result for early-stop
        current_turn = state.get("current_turn", {})
        evaluation   = current_turn.get("evaluation") if isinstance(current_turn, dict) else None

        # Always run to max_iterations — breach does not cause early exit.
        if iteration >= max_iters:
            step("RedGen routing: max iterations reached", iteration=iteration)
            return RoutingSignals.END

        debug("RedGen routing: continue", iteration=iteration, max=max_iters)
        return RoutingSignals.CONTINUE

    @classmethod
    def get_dependency_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Payload domain to attack from.",
                    "enum": ["cybersecurity", "harmful", "illegal",
                             "harassment", "misinformation", "copyright"],
                    "default": "cybersecurity"
                },
                "model": {
                    "type": "string",
                    "description": "Ollama model for paraphrasing (e.g. 'llama3.2:latest').",
                    "default": "huihui_ai/dolphin3-abliterated:latest"
                },
                "llm_provider_name": {
                    "type": "string",
                    "description": "Provider for paraphrasing.",
                    "enum": ["ollama", "gemini"],
                    "default": "ollama"
                },
                "paraphrase": {
                    "type": "boolean",
                    "description": "Use LLM to paraphrase payload before templating.",
                    "default": True
                },
                "encode_ratio": {
                    "type": "number",
                    "description": "Probability (0–1) of applying an encoding mutation per turn.",
                    "default": 0.3
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Maximum number of attack turns.",
                    "default": 10
                },
                "target_score": {
                    "type": "number",
                    "description": "Deprecated — routing always runs to max_iterations.",
                    "default": 0.8
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducible prompt selection.",
                    "default": 42
                }
            },
            "required": ["model"]
        }
