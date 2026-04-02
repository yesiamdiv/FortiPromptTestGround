"""
redgen/generator.py
────────────────────
Research-grade test case generator inspired by HarmBench / AdvBench.
Modified to provide a strict number of N attack prompts with scaling diversity.
"""

import asyncio
import random
import copy
import os
import math
from typing import Optional, Dict, Any

import pandas as pd
from datetime import datetime, timezone

from api_gateway import APIGateway

from .redgen_payloads.loader import (
    load_templates,
    load_payloads_from_domain,
)
from .redgen_payloads.templates import apply_template_by_name

from .augmentation.encoding import (
    apply_encoding,
    AVAILABLE_LANGUAGES,
    AVAILABLE_ENCODINGS,
)

from .engines.ollama_engine import OllamaEngine

# ─────────────────────────────────────────────

class TestCaseGenerator:

    def __init__(
        self,
        n: int,
        domain: str = "cybersecurity",
        paraphrase: bool = True,
        encode_ratio: float = 0.3,
        seed: int = 42,
        engine: str = "ollama",                # "groq" or "ollama"
        ollama_model: Optional[str] = None,    # used when engine="ollama"
        output_dir: str = "./output",          # directory to save prompts
        api_gateway: APIGateway = None,
    ):
        self.api_gateway = api_gateway
        self.run_id = None 
        self.n = n  # The strict target number of prompts
        self.domain = domain
        self.seed = seed
        self.paraphrase = paraphrase
        self.encode_ratio = encode_ratio

        random.seed(seed)

        print(f"\n[Loading] Payloads for domain '{domain}'")
        self.payloads = load_payloads_from_domain(domain)
        print(f"  Loaded {len(self.payloads)} payloads")

        print("[Loading] Templates")
        self.templates = load_templates()
        print(f"  Loaded {len(self.templates)} templates")

        self.engine = engine
        self.ollama_model = ollama_model
        self.output_dir = output_dir
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        # Initialize LLM engine
        if engine == "ollama":
            self.llm = OllamaEngine(model=self.ollama_model or "dolphin-mistral:7b-v2.6")
        else:
            raise ValueError(f"Unknown engine '{engine}'")

    # ─────────────────────────────────────────────

    def _get_sample_sizes(self):
        """
        Calculates how many templates and payloads to pick to satisfy N.
        Uses a square root approach so diversity scales with volume.
        """
        # Aim for a balanced grid where T * P ≈ N
        base = math.ceil(math.sqrt(self.n))
        
        n_templates = min(len(self.templates), base)
        # Ensure n_payloads is large enough to reach N even if templates are limited
        n_payloads = math.ceil(self.n / n_templates)
        
        return n_templates, n_payloads

    async def emit_event(self, event_name: str, data: Dict[str, Any]):
        if self.api_gateway and self.run_id:
            await self.api_gateway.emit_event(
                event_name=event_name,
                data=data,
                run_id=self.run_id
            )
        else:
            print(f"Warning: API Gateway or run_id not set. Cannot emit event: {event_name}")

    def _sample(self, pool, k):
        k = min(k, len(pool))
        return random.sample(pool, k)

    async def _paraphrase(self, text):
        if not self.llm:
            return None
        try:
            return await self.llm.paraphrase(text)
        except Exception:
            return None

    def _generate_prompt(self, template, payload):
        prompt = apply_template_by_name(template["name"], payload["text"], domain=self.domain)

        severity = max(
            template.get("severity", 5),
            payload.get("severity", 5),
        )

        return {
            "attack_type": template.get("attack_type", "unknown"),
            "payload_category": payload.get("category", self.domain),
            "severity": severity,
            "template_id": template.get("id", "unknown"),
            "payload_id": payload.get("id", "unknown"),
            "generation_mode": (
                f"T:{template.get('generation_mode','original')} | "
                f"P:{payload.get('generation_mode','original')}"
            ),
            "language": payload.get("language", "english"),
            "encoding": payload.get("encoding", "none"),
            "prompt": prompt,
        }

    # ─────────────────────────────────────────────
    
    def generate_sync_wrapper(self, run_id, run_counter):
        return asyncio.run(self.generate(run_id=run_id, run_counter=run_counter))
    
    async def generate(self, run_id: str = None, run_counter: int = None) -> pd.DataFrame:
        self.run_id = run_id
        if not self.run_id:
            raise ValueError("run_id must be provided to generate prompts")

        # 1. Determine optimal sample sizes to reach target N
        n_t, n_p = self._get_sample_sizes()
        
        sampled_templates = self._sample(self.templates, n_t)
        sampled_payloads = self._sample(self.payloads, n_p)

        # 2. Create the Cartesian product of (Template, Payload)
        # We use a list of pairs so we can shuffle and truncate to exactly N
        all_combinations = []
        for t in sampled_templates:
            for p in sampled_payloads:
                all_combinations.append((t, copy.deepcopy(p)))
        
        # Shuffle combinations to ensure varied output if we truncate
        random.shuffle(all_combinations)

        # 3. Truncate to EXACTLY n
        final_worklist = all_combinations[:self.n]
        total_prompts = len(final_worklist)

        prompts = []
        generated_count = 0

        # 4. Process each pair
        for template, payload in final_worklist:
            processed_payload_text = payload["text"]
            
            # PARAPHRASE (LLM Intervention)
            if self.paraphrase:
                para = await self._paraphrase(processed_payload_text)
                if para:
                    processed_payload_text = para
                    payload["generation_mode"] = "paraphrased"

            # ENCODING (Probabilistic Transformation)
            # Instead of adding new items, we transform the current one based on ratio
            if random.random() < self.encode_ratio:
                encoded_result = apply_encoding(
                    processed_payload_text,
                    language=random.choice(AVAILABLE_LANGUAGES),
                    encoding=random.choice(AVAILABLE_ENCODINGS),
                )
                processed_payload_text = encoded_result["text"]
                payload["language"] = encoded_result["language"]
                payload["encoding"] = encoded_result["encoding"]
                payload["generation_mode"] = (
                    payload.get("generation_mode", "original") + "+encoded"
                )

            # Update the payload object with finalized text before templating
            payload["text"] = processed_payload_text
            
            # Construct final prompt string
            prompt_data = self._generate_prompt(template, payload)
            prompts.append(prompt_data)
            generated_count += 1

            # Emit attack_generated event
            await self.api_gateway.socket_manager.send_attack_event_to_frontend(
                run_id=self.run_id,
                event_name="attack_generated",
                data={
                    "runId": self.run_id,
                    "prompt": {
                        "promptId": f"prompt-{generated_count}",
                        "content": prompt_data["prompt"],
                        "status": "generated",
                        "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
                    }
                }
            )

            # Emit stats updates
            if generated_count % 10 == 0 or generated_count == total_prompts:
                await self.api_gateway.socket_manager.send_attack_event_to_frontend(
                    run_id=self.run_id,
                    event_name="attack_stats_updated",
                    data={
                        "runId": self.run_id,
                        "stats": {
                            "totalPrompts": total_prompts,
                            "pendingAttacks": total_prompts - generated_count,
                            "attacksGenerated": generated_count,
                        }
                    }
                )

        # Final Completion Event
        await self.api_gateway.socket_manager.send_attack_event_to_frontend(
            run_id=self.run_id,
            event_name="attack_completed",
            data={
                "runId": self.run_id,
                "finalStats": {
                    "totalPrompts": total_prompts,
                    "pendingAttacks": 0,
                    "attacksGenerated": total_prompts,
                }
            }
        )

        return pd.DataFrame(prompts)