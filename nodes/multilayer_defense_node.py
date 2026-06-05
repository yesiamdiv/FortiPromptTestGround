"""
Multilayer Defense Node — Multi-stage AI-powered prompt injection defense system.

Architecture:
- Layer 1 (Ensemble ML): BoW+LR, BoW+GB, TF-IDF+RF → Early exit gate
- Layer 2 (BERT-BiLSTM): Deep contextual understanding + Category LR fallback
- Layer 3 (Harmful Content Detector): Final gate for violence/weapons/abuse detection

All model paths are relative to nodes/data/ directory.

IMPORTANT: Uses singleton pattern to prevent repeated model loading.
"""

import os
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional

import torch
import torch.nn as nn
import joblib
from transformers import (
    BertTokenizer, BertModel,
    AutoTokenizer, AutoModelForSequenceClassification,
)
from sklearn.pipeline import Pipeline

from nodes.base import BaseAdversarialNode
from nodes.llm_forwarding_mixin import LLMForwardingMixin
from engine.state import SystemState
from core.logging import tracer, step, err

# ─── CONFIG (Relative Paths) ────────────────────────────────────────
MODEL_DIR = Path(os.path.join(os.path.dirname(__file__), "data"))

BINARY_MODELS = {
    "BoW+LR"   : MODEL_DIR / "BoW__Logistic_Regression.joblib",
    "BoW+GB"   : MODEL_DIR / "BoW__Gradient_Boosting.joblib",
    "TF-IDF+RF": MODEL_DIR / "TF-IDF__Random_Forest.joblib",
}
VECTORIZER_PATH  = MODEL_DIR / "vectorizer.pkl"
CATEGORY_LR_PATH = MODEL_DIR / "category_model.pkl"
CATEGORY_LE_PATH = MODEL_DIR / "label_encoder.pkl"

BERT_CKPT_PATH        = MODEL_DIR / "fortiprompt_bert_rnn.pt"
BERT_LE_PATH          = MODEL_DIR / "bert_label_encoder.pkl"
HARMFUL_DETECTOR_DIR  = MODEL_DIR / "fortiprompt_harmful_detector"

HARMFUL_LABEL_MAP     = {0: "BENIGN", 1: "MALICIOUS"}
HARMFUL_MALICIOUS_IDS = {1}

# Decision thresholds (configurable via node_params)
DEFAULT_ENSEMBLE_VOTE_THRESHOLD = 2
DEFAULT_BERT_OVERRIDE_CONF      = 0.85
DEFAULT_BERT_MEDIUM_CONF        = 0.60
DEFAULT_BERT_CATEGORY_CONF      = 0.80
DEFAULT_HARMFUL_CONF_THRESHOLD  = 0.75

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ─── SINGLETON DEFENSE SYSTEM ────────────────────────────────────────
_defense_system_instance: Optional['DefenseSystem'] = None
_defense_system_lock = asyncio.Lock()  # For thread-safe initialization


async def get_defense_system(
    ensemble_vote_threshold: int = DEFAULT_ENSEMBLE_VOTE_THRESHOLD,
    bert_override_conf: float = DEFAULT_BERT_OVERRIDE_CONF,
    bert_medium_conf: float = DEFAULT_BERT_MEDIUM_CONF,
    bert_category_conf: float = DEFAULT_BERT_CATEGORY_CONF,
    harmful_conf_threshold: float = DEFAULT_HARMFUL_CONF_THRESHOLD
) -> 'DefenseSystem':
    """
    Get or create the singleton DefenseSystem instance.
    Thread-safe lazy initialization using asyncio.Lock.
    
    This prevents models from being loaded multiple times, which was causing
    the application to freeze when API endpoints were called.
    """
    global _defense_system_instance
    
    if _defense_system_instance is not None:
        # Instance exists, just update thresholds if needed
        _defense_system_instance.ENSEMBLE_VOTE_THRESHOLD = ensemble_vote_threshold
        _defense_system_instance.BERT_OVERRIDE_CONF = bert_override_conf
        _defense_system_instance.BERT_MEDIUM_CONF = bert_medium_conf
        _defense_system_instance.BERT_CATEGORY_CONF = bert_category_conf
        _defense_system_instance.HARMFUL_CONF_THRESHOLD = harmful_conf_threshold
        return _defense_system_instance
    
    # Need to create instance - acquire lock
    async with _defense_system_lock:
        # Double-check after acquiring lock (prevent race condition)
        if _defense_system_instance is not None:
            _defense_system_instance.ENSEMBLE_VOTE_THRESHOLD = ensemble_vote_threshold
            _defense_system_instance.BERT_OVERRIDE_CONF = bert_override_conf
            _defense_system_instance.BERT_MEDIUM_CONF = bert_medium_conf
            _defense_system_instance.BERT_CATEGORY_CONF = bert_category_conf
            _defense_system_instance.HARMFUL_CONF_THRESHOLD = harmful_conf_threshold
            return _defense_system_instance
        
        # Create the singleton instance
        print("\n" + "="*70)
        print("[DefenseSystem]  Initializing singleton instance (ONE-TIME LOAD)")
        print("="*70)
        _defense_system_instance = DefenseSystem(
            binary_models_paths=BINARY_MODELS,
            vectorizer_path=VECTORIZER_PATH,
            category_lr_path=CATEGORY_LR_PATH,
            category_le_path=CATEGORY_LE_PATH,
            bert_ckpt_path=BERT_CKPT_PATH,
            bert_le_path=BERT_LE_PATH,
            harmful_detector_dir=HARMFUL_DETECTOR_DIR,
            ensemble_vote_threshold=ensemble_vote_threshold,
            bert_override_conf=bert_override_conf,
            bert_medium_conf=bert_medium_conf,
            bert_category_conf=bert_category_conf,
            harmful_conf_threshold=harmful_conf_threshold,
            device=DEVICE
        )
        print("[DefenseSystem]  Singleton ready - subsequent calls will reuse this instance")
        print("="*70 + "\n")
        return _defense_system_instance


# ─── BERT-RNN MODEL ─────────────────────────────────────────────────
class BertRNNClassifier(nn.Module):
    def __init__(self, model_name, num_classes, rnn_type="LSTM",
                 hidden_size=128, num_layers=2, bidirectional=True, dropout=0.3):
        super().__init__()
        self.bert          = BertModel.from_pretrained(model_name)
        self.rnn_type      = rnn_type.upper()
        self.bidirectional = bidirectional

        RNNClass = nn.LSTM if self.rnn_type == "LSTM" else nn.GRU
        self.rnn = RNNClass(
            input_size    = self.bert.config.hidden_size,
            hidden_size   = hidden_size,
            num_layers    = num_layers,
            batch_first   = True,
            bidirectional = bidirectional,
            dropout       = dropout if num_layers > 1 else 0.0,
        )
        rnn_out_dim  = hidden_size * (2 if bidirectional else 1)
        self.dropout = nn.Dropout(dropout)
        self.fc      = nn.Linear(rnn_out_dim, num_classes)

    def forward(self, input_ids, attention_mask):
        seq_out = self.bert(
            input_ids=input_ids, attention_mask=attention_mask
        ).last_hidden_state

        if self.rnn_type == "LSTM":
            _, (hidden, _) = self.rnn(seq_out)
        else:
            _, hidden = self.rnn(seq_out)

        hidden = (
            torch.cat((hidden[-2], hidden[-1]), dim=1)
            if self.bidirectional else hidden[-1]
        )
        return self.fc(self.dropout(hidden))


# ─── DEFENSE SYSTEM ─────────────────────────────────────────────────
class DefenseSystem:
    def __init__(self, binary_models_paths: Dict[str, Path], vectorizer_path: Path,
                 category_lr_path: Path, category_le_path: Path,
                 bert_ckpt_path: Optional[Path], bert_le_path: Optional[Path],
                 harmful_detector_dir: Optional[Path],
                 ensemble_vote_threshold: int, bert_override_conf: float,
                 bert_medium_conf: float, bert_category_conf: float,
                 harmful_conf_threshold: float, device: torch.device):
        print("  Loading models for DefenseSystem...")

        self.device = device

        # L1 deps
        try:
            self.vectorizer       = joblib.load(str(vectorizer_path))
            self.category_lr      = joblib.load(str(category_lr_path))
            self.label_encoder_lr = joblib.load(str(category_le_path))
            self.binary_models    = {n: joblib.load(str(p)) for n, p in binary_models_paths.items()}
            print(f"   [L1] Ensemble models loaded ({list(self.binary_models.keys())})")
        except Exception as e:
            print(f"   [L1] Failed to load ensemble models: {e}. Layer 1 will be unavailable.")
            self.vectorizer = None
            self.category_lr = None
            self.label_encoder_lr = None
            self.binary_models = {}

        # L2 — BERT-BiLSTM
        self.bert_model         = None
        self.bert_tokenizer     = None
        self.label_encoder_bert = None
        self.bert_available     = False

        if bert_ckpt_path and bert_ckpt_path.exists() and bert_le_path and bert_le_path.exists():
            try:
                ckpt = torch.load(str(bert_ckpt_path), map_location=self.device)
                cfg  = ckpt["config"]
                self.bert_model = BertRNNClassifier(
                    model_name    = cfg["model_name"],
                    num_classes   = ckpt["num_classes"],
                    rnn_type      = cfg["rnn_type"],
                    hidden_size   = cfg["hidden_size"],
                    num_layers    = cfg["num_layers"],
                    bidirectional = cfg["bidirectional"],
                    dropout       = cfg["rnn_dropout"],
                ).to(self.device)
                self.bert_model.load_state_dict(ckpt["model_state_dict"])
                self.bert_model.eval()
                self.bert_tokenizer     = BertTokenizer.from_pretrained(cfg["model_name"])
                self.label_encoder_bert = joblib.load(str(bert_le_path))
                self.bert_available     = True
                print(f"   [L2] BERT-BiLSTM      loaded  | classes: {list(self.label_encoder_bert.classes_)}")
            except Exception as e:
                print(f"    [L2] BERT-BiLSTM failed: {e} → LR-only mode")
        else:
            print(f"    [L2] BERT checkpoint or label encoder not found → LR-only mode")

        # L3 — Harmful Content Detector
        self.harmful_tokenizer = None
        self.harmful_model     = None
        self.harmful_available = False

        if harmful_detector_dir and harmful_detector_dir.exists():
            try:
                self.harmful_tokenizer = AutoTokenizer.from_pretrained(str(harmful_detector_dir))
                self.harmful_model     = AutoModelForSequenceClassification.from_pretrained(
                                             str(harmful_detector_dir)).to(self.device)
                self.harmful_model.eval()
                self.harmful_available = True
                print(f"  [L3] Harmful Detector loaded  ({harmful_detector_dir.name})")
            except Exception as e:
                print(f"  [L3] Harmful Detector failed: {e}")
        else:
            print(f"  [L3] Harmful Detector directory not found at {harmful_detector_dir}")

        # Store thresholds
        self.ENSEMBLE_VOTE_THRESHOLD = ensemble_vote_threshold
        self.BERT_OVERRIDE_CONF      = bert_override_conf
        self.BERT_MEDIUM_CONF        = bert_medium_conf
        self.BERT_CATEGORY_CONF      = bert_category_conf
        self.HARMFUL_CONF_THRESHOLD  = harmful_conf_threshold

        print(f"\n  Device : {self.device}")
        print(f"  Layers : L1=Ensemble → L2=BERT+LR → L3=HarmfulDetector [final gate]")
        print(f"  DefenseSystem ready.\n")

    # ── Layer 1: Ensemble ML ──────────────────────────────────────
    def layer1_ensemble(self, text):
        if not self.binary_models:
            return {"verdict": None, "votes": 0, "category": None}

        clean = text.lower().strip()
        X = self.vectorizer.transform([clean]) if self.vectorizer else None

        preds = []
        for name, model in self.binary_models.items():
            inp = [clean] if isinstance(model, Pipeline) else X
            try:
                pred = int(model.predict(inp)[0])
                prob = float(model.predict_proba(inp)[0][1])
            except Exception:
                pred = int(model.predict(inp)[0])
                prob = 0.5
            preds.append({"name": name, "pred": pred, "conf": prob})

        votes = sum(r["pred"] for r in preds)
        verdict = "MALICIOUS" if votes >= self.ENSEMBLE_VOTE_THRESHOLD else "BENIGN"
        avg_conf = sum(r["conf"] for r in preds) / len(preds) if preds else 0.0

        return {"verdict": verdict, "votes": int(votes), "category": None, "avg_conf": avg_conf, "predictions": preds, "_X": X}

    # ── Layer 2: BERT-BiLSTM ──────────────────────────────────────
    def layer2_bert(self, text):
        if not self.bert_available:
            return self._layer2_fallback_lr(text)

        try:
            enc = self.bert_tokenizer(
                text, return_tensors="pt", padding=True,
                truncation=True, max_length=128
            )
            enc = {k: v.to(self.device) for k, v in enc.items()}

            with torch.no_grad():
                logits = self.bert_model(enc["input_ids"], enc["attention_mask"])
                probs = torch.softmax(logits, dim=1)[0]
                pred_idx = torch.argmax(probs).item()
                conf = float(probs[pred_idx].item())

            pred_label = str(self.label_encoder_bert.inverse_transform([pred_idx])[0])
            verdict = "BENIGN" if pred_label == "benign" else "MALICIOUS"

            return {
                "verdict": verdict,
                "confidence": conf,
                "category": pred_label,
                "source": "BERT"
            }
        except Exception as e:
            print(f"   BERT inference failed: {e}, falling back to LR")
            return self._layer2_fallback_lr(text)

    def _layer2_fallback_lr(self, text):
        if not self.category_lr or not self.label_encoder_lr:
            return {"verdict": None, "confidence": 0.0, "category": None, "source": "NONE"}

        pred = int(self.category_lr.predict([text])[0])
        proba = self.category_lr.predict_proba([text])[0]
        conf = float(max(proba))
        category = str(self.label_encoder_lr.inverse_transform([pred])[0])
        verdict = "BENIGN" if category == "benign" else "MALICIOUS"

        return {
            "verdict": verdict,
            "confidence": conf,
            "category": category,
            "source": "LR"
        }

    # ── Layer 3: Harmful Content Detector ─────────────────────────
    def layer3_harmful(self, text):
        if not self.harmful_available:
            return {"verdict": None, "confidence": 0.0}

        try:
            enc = self.harmful_tokenizer(
                text, return_tensors="pt", padding=True,
                truncation=True, max_length=512
            )
            enc = {k: v.to(self.device) for k, v in enc.items()}

            with torch.no_grad():
                outputs = self.harmful_model(**enc)
                probs = torch.softmax(outputs.logits, dim=1)[0]
                pred_idx = torch.argmax(probs).item()
                conf = float(probs[pred_idx].item())

            verdict = HARMFUL_LABEL_MAP.get(pred_idx, "UNKNOWN")
            return {"verdict": verdict, "confidence": conf}
        except Exception as e:
            print(f"   Harmful detector failed: {e}")
            return {"verdict": None, "confidence": 0.0}

    # ── Category Resolution (replicates FastAPI layer2_category_lr) ──
    def _resolve_category(self, text, l2_res):
        if not self.category_lr or not self.label_encoder_lr:
            return l2_res.get("category", "benign") if l2_res else "benign"

        X = None
        if self.vectorizer:
            X = self.vectorizer.transform([text.lower().strip()])

        lr_probs = self.category_lr.predict_proba(X)[0] if X is not None else None
        if lr_probs is not None:
            lr_idx = lr_probs.argmax()
            lr_cat = str(self.label_encoder_lr.inverse_transform([lr_idx])[0])
            lr_conf = float(lr_probs[lr_idx])
        else:
            lr_cat = "benign"
            lr_conf = 0.0

        if l2_res and l2_res.get("confidence", 0) >= self.BERT_CATEGORY_CONF:
            return l2_res.get("category", lr_cat)
        return lr_cat

    # ── Main Prediction Pipeline ──────────────────────────────────
    def predict(self, text: str) -> Dict[str, Any]:
        """
        Execute the multi-layer defense pipeline.
        
        No early exit on L1 — always proceeds to L2/L3 (matching FastAPI flow).
        L1 MALICIOUS continues to deeper layers rather than blocking immediately.
        """
        result = {
            "blocked_at": None,
            "decision_source": None,
            "category": "unknown",
            "confidence": 0.0,
            "l1_verdict": None,
            "l2_verdict": None,
            "l3_verdict": None,
        }

        # ── Layer 1 ───────────────────────────────────────────────
        l1 = self.layer1_ensemble(text)
        result["l1_verdict"] = l1

        # ── Layer 2 ───────────────────────────────────────────────
        l2 = self.layer2_bert(text)
        result["l2_verdict"] = l2

        l2_flag = False
        decision_source = "ENSEMBLE_ONLY"

        if l2["confidence"] is not None:
            if l2["confidence"] >= self.BERT_OVERRIDE_CONF:
                l2_flag = l2["verdict"] == "MALICIOUS"
                decision_source = "BERT"
            elif l2["confidence"] >= self.BERT_MEDIUM_CONF:
                l2_flag = l2["verdict"] == "MALICIOUS"
                decision_source = "BERT+ENSEMBLE"

        # ── Layer 3 (Final Gate) ──────────────────────────────────
        l3 = self.layer3_harmful(text)
        result["l3_verdict"] = l3

        harmful_flagged = (
            l3["verdict"] == "MALICIOUS" and l3["confidence"] >= self.HARMFUL_CONF_THRESHOLD
        )

        # ── Decision ──────────────────────────────────────────────
        if l2_flag or harmful_flagged:
            if l2_flag and harmful_flagged:
                blocked_at = "L2+3_BERT_HARMFUL"
            elif l2_flag:
                blocked_at = "L2_BERT"
            else:
                blocked_at = "L3_HARMFUL_DETECTOR"

            cat = self._resolve_category(text, l2)
            result["blocked_at"] = blocked_at
            result["decision_source"] = decision_source
            result["category"] = cat if cat.lower() != "benign" else "harmful_content"
            result["confidence"] = float(max(
                l2.get("confidence", 0) if l2["confidence"] is not None else 0,
                l3.get("confidence", 0),
            ))
            return result

        # ── All layers passed → ALLOW ─────────────────────────────
        result["decision_source"] = "ALL_LAYERS_PASSED"
        result["category"] = self._resolve_category(text, l2)
        result["confidence"] = float(max(
            l2.get("confidence", 0) if l2["confidence"] is not None else 0,
            l3.get("confidence", 0),
        ))
        return result


# ─── NODE CLASS ─────────────────────────────────────────────────────
class MultilayerDefenseNode(LLMForwardingMixin, BaseAdversarialNode):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config=config)

        self.name = config.get('name', self.__class__.__name__)
        node_params = config.get("node_params", {})
        
        # Initialize LLM forwarding
        self._init_llm_forwarding(node_params)
        
        # Extract thresholds from config
        self.ensemble_vote_threshold = node_params.get("ensemble_vote_threshold", DEFAULT_ENSEMBLE_VOTE_THRESHOLD)
        self.bert_override_conf      = node_params.get("bert_override_conf", DEFAULT_BERT_OVERRIDE_CONF)
        self.bert_medium_conf        = node_params.get("bert_medium_conf", DEFAULT_BERT_MEDIUM_CONF)
        self.bert_category_conf      = node_params.get("bert_category_conf", DEFAULT_BERT_CATEGORY_CONF)
        self.harmful_conf_threshold  = node_params.get("harmful_conf_threshold", DEFAULT_HARMFUL_CONF_THRESHOLD)
        
        # Defense system will be lazily initialized in execute()
        self.defense_system: Optional[DefenseSystem] = None
        self._initialization_complete = False

    async def initialize_defense_system(self):
        """Lazy initialization of defense system - gets singleton instance."""
        if self._initialization_complete:
            return
        
        tracer(f"Getting DefenseSystem singleton for: {self.name}")
        
        try:
            self.defense_system = await get_defense_system(
                ensemble_vote_threshold=self.ensemble_vote_threshold,
                bert_override_conf=self.bert_override_conf,
                bert_medium_conf=self.bert_medium_conf,
                bert_category_conf=self.bert_category_conf,
                harmful_conf_threshold=self.harmful_conf_threshold
            )
            self._log_capability_summary()
            self._initialization_complete = True
            
        except Exception as e:
            err(f"DefenseSystem singleton retrieval failed: {e}")
            self.defense_system = None
            self._initialization_complete = False

    def _log_capability_summary(self):
        if self.defense_system is None:
            print(f"[MultilayerDefense:{self.name}] OFFLINE — defense system failed to initialise.")
            return

        ds = self.defense_system
        l1_ok = bool(ds.vectorizer and ds.binary_models)
        l2_ok = getattr(ds, "bert_available", False)
        l3_ok = getattr(ds, "harmful_available", False)

        layers = []
        layers.append(f"L1-Ensemble={'OK (' + ','.join(ds.binary_models.keys()) + ')' if l1_ok else 'MISSING'}")
        layers.append(f"L2-BERT={'OK' if l2_ok else 'SKIPPED'}")
        layers.append(f"L3-HarmfulDetector={'OK' if l3_ok else 'SKIPPED'}")

        active_count = sum([l1_ok, l2_ok, l3_ok])
        status = "FULL" if active_count == 3 else f"PARTIAL ({active_count}/3 layers)"
        print(f"[MultilayerDefense:{self.name}] {status}")
        for layer in layers:
            print(f"  {layer}")

    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        if runtime_config is None:
            runtime_config = {}

        # Lazy initialization of defense system
        if not self._initialization_complete:
            await self.initialize_defense_system()

        if self.defense_system is None:
            from core.models import create_defence_response
            error_defence = create_defence_response("Defense system not initialized", status_code=500)
            return {"current_turn": {"defence": error_defence, "node_name": self.name}}
            
        tracer(f"Executing Multilayer Defense: {self.name}")
        
        # STRICT STATE ACCESS
        if "current_turn" not in state:
            raise ValueError("Corrupted state: Missing 'current_turn'.")
            
        current_turn = state["current_turn"]
        attack = current_turn.get("attack")
        
        input_prompt = attack.to_string() if attack else ""

        if not input_prompt:
            print("Warning: No input prompt found in state.")

        try:
            # Run ML prediction
            result = self.defense_system.predict(input_prompt)
            step("Defense pipeline executed successfully")
            
            # Determine final allow/block decision based on layer verdicts
            blocked_at = result.get("blocked_at")
            is_blocked = blocked_at is not None

            status_code = 403 if is_blocked else 200

            # Extract additional info for display
            category = result.get("category", "unknown")
            confidence = result.get("confidence", 0.0)
            decision_source = result.get("decision_source", "unknown")

            # Build user-friendly response text with emojis
            if is_blocked:
                response_text = f"Request blocked by {blocked_at}\n"
                response_text += f"Category: {category}\n"
                response_text += f"Confidence: {confidence:.2%}"
            else:
                response_text = "Request passed all defense layers"

            # Create metadata for structured access (for UI display)
            metadata = {
                "category": category,
                "is_malicious": is_blocked,
                "blocked_by": blocked_at if is_blocked else None,
                "confidence": float(confidence),
                "decision_source": decision_source,
                # Include layer-specific details for debugging
                "layer_details": {
                    "l1_verdict": result.get("l1_verdict"),
                    "l2_verdict": result.get("l2_verdict"),
                    "l3_verdict": result.get("l3_verdict"),
                }
            }
            
            from core.models import create_defence_response
            defence_payload = create_defence_response(
                text=response_text,
                status_code=status_code,
                headers={"x-decision-source": str(decision_source)},
                metadata=metadata  # Structured data for UI
            )

            # Forward to LLM if enabled
            defence_payload = await self.maybe_forward_to_llm(
                defence_payload, input_prompt, runtime_config
            )

            return {
                "current_turn": {
                    "defence": defence_payload,
                    "node_name": self.name
                }
            }

        except Exception as e:
            err(f"Defense system prediction failed: {e}")
            from core.models import create_defence_response
            error_defence = create_defence_response(f"Defense system failed: {e}", status_code=500)
            return {"current_turn": {"defence": error_defence, "node_name": self.name}}

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "ensemble_vote_threshold": {
                    "type": "integer",
                    "description": "L1 ensemble models that must vote malicious to trigger a block (out of 3).",
                    "default": 2,
                    "minimum": 1,
                    "maximum": 3
                },
                "bert_override_conf": {
                    "type": "number",
                    "description": "L2 BERT confidence above which the BERT verdict overrides L1 ensemble.",
                    "default": 0.85,
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "bert_medium_conf": {
                    "type": "number",
                    "description": "L2 BERT confidence above which a medium-confidence flag is accepted.",
                    "default": 0.60,
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "bert_category_conf": {
                    "type": "number",
                    "description": "L2 BERT confidence above which BERT's category label is used instead of L1's.",
                    "default": 0.80,
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "harmful_conf_threshold": {
                    "type": "number",
                    "description": "L3 harmful-content detector confidence required to trigger a block.",
                    "default": 0.75,
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                **LLMForwardingMixin.llm_forwarding_schema_fragment(),
            },
            "required": []
        }