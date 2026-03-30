"""
redgen/generator.py
────────────────────
Research-grade test case generator inspired by HarmBench / AdvBench.

Pipeline
--------
1. Sample templates
2. Sample payloads
3. Paraphrase templates/payloads via LLM
4. Apply encoding + language mutations
5. Combine templates × payloads
6. Return pandas dataframe
"""

import asyncio
import random
import copy
import os
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
        engine: str = "groq",                # "groq" or "ollama"
        ollama_model: Optional[str] = None,    # used when engine="ollama"
        output_dir: str = "./output",    # directory to save prompts
        api_gateway: APIGateway = None,
    ):
        self.api_gateway = api_gateway
        self.run_id = None # Initialize run_id here
        self.n = n
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
        self.llm = OllamaEngine(model=self.ollama_model or "dolphin-mistral:7b-v2.6")
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        if paraphrase:
            if engine == "ollama":
  
                self.llm = OllamaEngine(model=self.ollama_model or "dolphin-mistral:7b-v2.6")
            else:
                raise ValueError(f"unknown engine '{engine}'")

    # ─────────────────────────────────────────────

    async def emit_event(self, event_name: str, data: Dict[str, Any]):
        if self.api_gateway and self.run_id:
            await self.api_gateway.emit_event(
            event_name=event_name,
                data=data,
                run_id=self.run_id
            )
        else:
            print(f"Warning: API Gateway or run_id not set. Cannot emit event: {event_name}")

    # ─────────────────────────────────────────────

    def _sample(self, pool, k):

        k = min(k, len(pool))
        return random.sample(pool, k)

    # ─────────────────────────────────────────────

    async def _paraphrase(self, text):

        if not self.llm:
            return None

        try:
            return await self.llm.paraphrase(text)
        except Exception:
            return None


    def _encode_payloads(self, payloads):

        encoded = []

        for p in payloads:

            if random.random() > self.encode_ratio:
                continue

            result = apply_encoding(
                p["text"],
                language=random.choice(AVAILABLE_LANGUAGES),
                encoding=random.choice(AVAILABLE_ENCODINGS),
            )

            item = copy.deepcopy(p)

            item["text"] = result["text"]
            item["language"] = result["language"]
            item["encoding"] = result["encoding"]

            item["generation_mode"] = (
                p.get("generation_mode", "original") + "+encoded"
            )

            encoded.append(item)

        return encoded

    # ─────────────────────────────────────────────

    def _generate_prompt(self, template, payload):

        prompt = apply_template_by_name(template["name"], payload["text"], domain=self.domain)

        severity = max(
            template.get("severity", 5),
            payload.get("severity", 5),
        )

        return {

            "attack_type": template.get("attack_type", "unknown"),

            "payload_category": payload.get(
                "category", self.domain
            ),

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
        self.run_id = run_id # Set the run_id
        if not self.run_id:
            raise ValueError("run_id must be provided to generate prompts")

        # Sample templates and payloads
        sampled_templates = self._sample(self.templates, k=self.n)
        sampled_payloads = self._sample(self.payloads, k=self.n)

        # Encode payloads
        encoded_payloads = self._encode_payloads(sampled_payloads)

        total_prompts = len(sampled_templates) * len(sampled_payloads + encoded_payloads)

        generated_count = 0
        # Combine templates and payloads to generate prompts
        prompts = []
        for template in sampled_templates:
            for payload in sampled_payloads + encoded_payloads:
                # Paraphrase if enabled and if the payload is not already paraphrased
                processed_payload_text = payload["text"]
                if self.paraphrase and payload.get("generation_mode", "original") == "original":
                    para = await self._paraphrase(payload["text"])
                    if para:
                        processed_payload_text = para
                        # Update payload generation mode for accurate reporting
                        payload["generation_mode"] = "paraphrased"

                # Apply encoding if applicable
                if payload.get("encoding"):
                    encoded_result = apply_encoding(
                        processed_payload_text,
                        language=payload.get("language", "english"),
                        encoding=payload.get("encoding", "none"),
                    )
                    processed_payload_text = encoded_result["text"]
                    payload["language"] = encoded_result["language"]
                    payload["encoding"] = encoded_result["encoding"]
                    # Update generation mode to reflect encoding
                    payload["generation_mode"] = (payload.get("generation_mode", "original") + "+encoded")

                prompt_data = self._generate_prompt(template, payload)
                prompts.append(prompt_data)
                generated_count += 1
                print(prompt_data,'"\n"')
                # Emit attack_generated event for each prompt
                await self.api_gateway.socket_manager.send_attack_event_to_frontend(
                    run_id=self.run_id,
                    event_name="attack_generated",
                    data={
                        "runId": self.run_id,
                        "prompt": {
                            "promptId": f"prompt-{generated_count}", # Simple ID generation
                            "content": prompt_data["prompt"],
                            "status": "generated",
                            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
                        }
                    }
                )

                # Emit attack_stats_updated periodically (e.g., every 10 prompts)
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

        # Emit attack_completed event after all prompts are generated
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