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

import random
import copy
import os
from typing import Optional

import pandas as pd

from .redgen_payloads.loader import (
    load_templates,
    load_payloads_from_domain,
    apply_template,
)

from .augmentation.encoding import (
    apply_encoding,
    AVAILABLE_LANGUAGES,
    AVAILABLE_ENCODINGS,
)

from .engines.ollama_engine import OllamaEngine
from api_gateway.main import api_gateway_instance as api_gateway
from api_gateway.main import APIGateway

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
        api_gateway: Optional[APIGateway] = api_gateway,    # used when engine="ollama"
        output_dir: str = "./output",    # directory to save prompts
    ):

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
        self.model = None
        self.llm = OllamaEngine(model=ollama_model or "dolphin-mistral:7b-v2.6")
        self.api_gateway = api_gateway
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        if paraphrase:
            if engine == "ollama":
  
                self.llm = OllamaEngine(model=ollama_model or "dolphin-mistral:7b-v2.6")
                self.model = self.llm.model
            else:
                raise ValueError(f"unknown engine '{engine}'")

    # ─────────────────────────────────────────────

    def _sample(self, pool, k):

        k = min(k, len(pool))
        return random.sample(pool, k)

    # ─────────────────────────────────────────────

    def _paraphrase(self, text):

        if not self.llm:
            return None

        try:
            return self.llm.paraphrase(text)
        except Exception:
            return None

    # ─────────────────────────────────────────────

    def _paraphrase_payloads(self, payloads):

        new_items = []

        for p in payloads:

            para = self._paraphrase(p["text"])

            if para:

                item = copy.deepcopy(p)
                item["text"] = para
                item["generation_mode"] = "paraphrased"

                new_items.append(item)

        return new_items

    # ─────────────────────────────────────────────
  
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

        prompt = apply_template(template, payload["text"])

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

    def generate(self) -> pd.DataFrame:

        k = max(2, self.n // 10)

        info = (
            f"\n[Generator] N={self.n}  "
            f"sample={k}  paraphrase={self.paraphrase}"
        )
        if self.paraphrase:
            info += f"  engine={self.engine} model={self.model}"
        print(info)

        # STEP 1 sample templates
        sel_templates = self._sample(self.templates, k)

        # STEP 2 sample payloads
        sel_payloads = self._sample(self.payloads, k)

        for t in sel_templates:
            t.setdefault("generation_mode", "original")

        for p in sel_payloads:
            p.setdefault("generation_mode", "original")

        # STEP 3 paraphrase
        para_payloads = []

        if self.paraphrase:

            print("\n[Paraphrasing payloads]")

            para_payloads = self._paraphrase_payloads(sel_payloads)

            print(f"  created {len(para_payloads)} paraphrased payloads")

        # STEP 4 encoding mutations

        all_payloads = sel_payloads + para_payloads

        encoded = self._encode_payloads(all_payloads)

        payload_pool = all_payloads + encoded

        print(f"Payload pool size = {len(payload_pool)}")

        # STEP 5 generate prompts and save/broadcast
        prompts_generated = []
        for i in range(self.n):
            template = random.choice(sel_templates)
            payload = random.choice(payload_pool)

            record = self._generate_prompt(template, payload)
            record["id"] = i + 1
            prompts_generated.append(record)

            # Save prompt to file
            prompt_text = record["prompt"]
            file_path = os.path.join(self.output_dir, f"attack_{record['id']}.txt")
            with open(file_path, "w") as f:
                f.write(prompt_text)

            # Broadcast prompt to frontend via API Gateway
            if self.api_gateway:
                # Assuming api_gateway has a method like send_prompt_to_frontend
                # We need to pass a run_id, which is not available here. 
                # For now, we'll use a placeholder or a generic broadcast.
                # In a real integration, this would be tied to a specific run.
                run_id = f"run_{self.run_counter}" # Placeholder run_id
                self.api_gateway.send_prompt_to_frontend(run_id, prompt_text)

        df = pd.DataFrame(prompts_generated)
        return df