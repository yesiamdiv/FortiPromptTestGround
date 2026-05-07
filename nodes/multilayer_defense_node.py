
# Filename: multilayer_defense_node.py

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

# Third-party imports for the defense logic
import torch
import torch.nn as nn
import joblib
from transformers import (
    BertTokenizer, BertModel,
    AutoTokenizer, AutoModelForSequenceClassification,
)
from sklearn.pipeline import Pipeline # Used in layer1_ensemble
# scikit-learn is also implicitly used by joblib.load for models trained with it.


# Project-specific imports for the node interface
from nodes.base import BaseAdversarialNode
from engine.state_schema import SystemState, RoutingSignals, TurnData

# -----------------------------------------------------------------
# CONFIG  (Adapted from final1.py)
# All model paths are now relative to this node's 'data' directory.
# -----------------------------------------------------------------
# Adjust MODEL_DIR to point to our project's data directory
# Assuming the script is in D:\Development\BE Project\AgenticTestingGround\AgenticLLMAdversarialTestbed\.worktrees\v2\nodes
# and data is in D:\Development\BE Project\AgenticTestingGround\AgenticLLMAdversarialTestbed\.worktrees\v2\nodes\data
MODEL_DIR = Path(os.path.join(os.path.dirname(__file__), "data"))

BINARY_MODELS = {
    "BoW+LR"   : MODEL_DIR / "BoW__Logistic_Regression.joblib",
    "BoW+GB"   : MODEL_DIR / "BoW__Gradient_Boosting.joblib",
    "TF-IDF+RF": MODEL_DIR / "TF-IDF__Random_Forest.joblib",
}
VECTORIZER_PATH  = MODEL_DIR / "vectorizer.pkl"
CATEGORY_LR_PATH = MODEL_DIR / "category_model.pkl"
CATEGORY_LE_PATH = MODEL_DIR / "label_encoder.pkl"

# BERT and Harmful Detector paths, now relative to MODEL_DIR.
# If these files were not explicitly copied to nodes/data, their loading will fail.
BERT_CKPT_PATH        = MODEL_DIR / "fortiprompt_bert_rnn.pt"
BERT_LE_PATH          = MODEL_DIR / "bert_label_encoder.pkl" # Renamed for clarity if different from CATEGORY_LE_PATH
HARMFUL_DETECTOR_DIR  = MODEL_DIR / "fortiprompt_harmful_detector" # This should be a directory within nodes/data

HARMFUL_LABEL_MAP     = {0: "BENIGN", 1: "MALICIOUS"} # CLASS_1 = malicious (confirmed)
HARMFUL_MALICIOUS_IDS = {1}

# Decision thresholds
ENSEMBLE_VOTE_THRESHOLD = 2     # votes needed out of 3 to flag
BERT_OVERRIDE_CONF      = 0.85  # BERT treated as high-confidence above this
BERT_MEDIUM_CONF        = 0.60  # BERT flag accepted at medium confidence
BERT_CATEGORY_CONF      = 0.80  # use BERT category above this, else LR
HARMFUL_CONF_THRESHOLD  = 0.75  # harmful detector blocks above this

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# -----------------------------------------------------------------
# BERT-RNN MODEL DEFINITION (Copied from final1.py)
# -----------------------------------------------------------------
class BertRNNClassifier(nn.Module):
    def __init__(self, model_name, num_classes, rnn_type="LSTM",
                 hidden_size=128, num_layers=2, bidirectional=True, dropout=0.3):
        super().__init__()
        # model_name here typically refers to a pre-trained BERT model name like 'bert-base-uncased'
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


# -----------------------------------------------------------------
# DEFENSE SYSTEM (Copied and modified from final1.py)
# Now accepts model paths in __init__ for better configurability
# -----------------------------------------------------------------
class DefenseSystem:
    def __init__(self, binary_models_paths: Dict[str, Path], vectorizer_path: Path,
                 category_lr_path: Path, category_le_path: Path,
                 bert_ckpt_path: Optional[Path], bert_le_path: Optional[Path],
                 harmful_detector_dir: Optional[Path],
                 ensemble_vote_threshold: int, bert_override_conf: float,
                 bert_medium_conf: float, bert_category_conf: float,
                 harmful_conf_threshold: float, device: torch.device):
        print("🔄  Loading models for DefenseSystem...")

        self.device = device

        # L1 deps
        try:
            self.vectorizer       = joblib.load(str(vectorizer_path))
            self.category_lr      = joblib.load(str(category_lr_path))
            self.label_encoder_lr = joblib.load(str(category_le_path))
            self.binary_models    = {n: joblib.load(str(p)) for n, p in binary_models_paths.items()}
            print(f"  ✅ [L1] Ensemble models loaded ({list(self.binary_models.keys())})")
        except Exception as e:
            print(f"  ❌ [L1] Failed to load ensemble models: {e}. Layer 1 will be unavailable.")
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
                print(f"  ✅ [L2] BERT-BiLSTM      loaded  | classes: {list(self.label_encoder_bert.classes_)}")
            except Exception as e:
                print(f"  ⚠️  [L2] BERT-BiLSTM failed: {e} → LR-only mode")
        else:
            print(f"  ⚠️  [L2] BERT checkpoint or label encoder not found → LR-only mode")

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
                print(f"  ✅ [L3] Harmful Detector loaded  ({harmful_detector_dir.name})")
            except Exception as e:
                print(f"  ⚠️  [L3] Harmful Detector failed: {e}")
        else:
            print(f"  ⚠️  [L3] Harmful Detector directory not found at {harmful_detector_dir}")

        # Store thresholds
        self.ENSEMBLE_VOTE_THRESHOLD = ensemble_vote_threshold
        self.BERT_OVERRIDE_CONF      = bert_override_conf
        self.BERT_MEDIUM_CONF        = bert_medium_conf
        self.BERT_CATEGORY_CONF      = bert_category_conf
        self.HARMFUL_CONF_THRESHOLD  = harmful_conf_threshold

        print(f"\n  🖥️  Device : {self.device}")
        print(f"  🛡️  Layers : L1=Ensemble → L2=BERT+LR → L3=HarmfulDetector [final gate]")
        print(f"✅  DefenseSystem ready.\n")

    # ── Layer 1: Ensemble ML ──────────────────────────────────────
    def layer1_ensemble(self, text):
        if not self.vectorizer or not self.binary_models:
            return 0, 0.0, [], None # If models failed to load, return benign

        clean = text.lower().strip()
        X     = self.vectorizer.transform([clean])
        preds = []

        for name, model in self.binary_models.items():
            inp = [clean] if isinstance(model, Pipeline) else X
            try:
                pred = int(model.predict(inp)[0])
                prob = float(model.predict_proba(inp)[0][1])
            except Exception: # Fallback for models that might not have predict_proba or other issues
                pred = int(model.predict(inp)[0])
                prob = 0.5
            preds.append({"name": name, "pred": pred, "conf": prob})

        votes    = sum(r["pred"] for r in preds)
        flag     = 1 if votes >= self.ENSEMBLE_VOTE_THRESHOLD else 0
        avg_conf = sum(r["conf"] for r in preds) / len(preds) if preds else 0.0
        return flag, avg_conf, preds, X

    # ── Layer 2: BERT-BiLSTM ──────────────────────────────────────
    def layer2_bert(self, text):
        if not self.bert_available:
            return None

        inputs = self.bert_tokenizer(
            text, return_tensors="pt", truncation=True,
            padding=True, max_length=128,
        ).to(self.device)

        with torch.no_grad():
            logits = self.bert_model(inputs["input_ids"], inputs["attention_mask"])
            probs  = torch.softmax(logits, dim=1)

        idx   = torch.argmax(probs, dim=1).item()
        conf  = probs[0][idx].item()
        label = self.label_encoder_bert.inverse_transform([idx])[0]

        return {
            "malicious" : 0 if label.lower() == "benign" else 1,
            "confidence": conf,
            "category"  : label,
            "all_probs" : {
                cls: round(probs[0][i].item(), 4)
                for i, cls in enumerate(self.label_encoder_bert.classes_)
            },
        }

    # ── Layer 2b: Category LR (support) ──────────────────────────
    def layer2_category_lr(self, X, bert_res):
        """
        BERT is primary; LR is fallback when BERT is uncertain.
        Always called after L2 to resolve category before L3.
        """
        if self.category_lr is None or self.label_encoder_lr is None:
            return "unknown", "N/A", 0.0 # Fallback if LR models failed to load

        lr_probs = self.category_lr.predict_proba(X)[0]
        lr_idx   = lr_probs.argmax()
        lr_cat   = self.label_encoder_lr.inverse_transform([lr_idx])[0]
        lr_conf  = float(lr_probs[lr_idx])

        if bert_res and bert_res["confidence"] >= self.BERT_CATEGORY_CONF:
            return bert_res["category"], "BERT", bert_res["confidence"]
        return lr_cat, "LR", lr_conf

    # ── Layer 3: Harmful Content Detector ────────────────────────
    def layer3_harmful(self, text):
        """
        Final gate — only reached when L1+L2 both passed.
        Catches harmful intent: violence, weapons, abuse, self-harm.
        """
        if not self.harmful_available:
            return None

        inputs = self.harmful_tokenizer(
            text, return_tensors="pt", truncation=True,
            padding=True, max_length=512,
        ).to(self.device)

        with torch.no_grad():
            probs = torch.softmax(self.harmful_model(**inputs).logits, dim=-1)[0]

        pred_id = probs.argmax().item()
        conf    = probs[pred_id].item()
        label   = HARMFUL_LABEL_MAP.get(pred_id, f"CLASS_{pred_id}")

        return {
            "malicious" : pred_id in HARMFUL_MALICIOUS_IDS,
            "label"     : label,
            "confidence": conf,
            "all_scores": {
                HARMFUL_LABEL_MAP.get(i, f"CLASS_{i}"): round(p.item(), 4)
                for i, p in enumerate(probs)
            },
        }

    # ── Full Cascading Pipeline ───────────────────────────────────
    def predict(self, text):
        result = {
            "text"            : text,
            "malicious"       : False,
            "category"        : "benign",
            "blocked_at"      : None,
            "decision_source" : None,
            "l2_flagged"      : False,
            "l2_decision_src" : None,
            "layer1"          : None,
            "layer2"          : None,
            "layer2_cat"      : None,
            "layer3"          : None,
        }

        # ── Layer 1 — early exit gate ─────────────────────────────
        l1_flag, l1_conf, l1_preds, X = self.layer1_ensemble(text)
        result["layer1"] = {
            "flag"    : l1_flag,
            "avg_conf": l1_conf,
            "models"  : l1_preds,
        }

        if l1_flag:
            # Hard stop — but run L2 for category resolution only
            bert_res = self.layer2_bert(text)
            category, cat_source, cat_conf = self.layer2_category_lr(X, bert_res)

            result["malicious"]       = True
            result["blocked_at"]      = "Layer 1 (Ensemble ML)"
            result["decision_source"] = "ENSEMBLE"
            result["category"]        = category if category.lower() != "benign" else "prompt_injection"
            result["layer2"]          = bert_res
            result["layer2_cat"]      = {
                "category": category,
                "source"  : cat_source,
                "conf"    : cat_conf,
            }
            return result

        # ── Layer 2 — contextual detection, no early block ────────
        # Runs fully: detects + resolves category, passes flag to L3
        bert_res = self.layer2_bert(text)
        result["layer2"] = bert_res

        l2_flag         = False
        decision_source = "ENSEMBLE_ONLY" # Default if BERT not available or low conf

        if bert_res:
            if bert_res["confidence"] >= self.BERT_OVERRIDE_CONF:
                l2_flag         = bool(bert_res["malicious"])
                decision_source = "BERT"
            elif bert_res["confidence"] >= self.BERT_MEDIUM_CONF:
                l2_flag         = bool(bert_res["malicious"])
                decision_source = "BERT+ENSEMBLE"

        # Record L2 flag — does NOT block here, hands off to L3
        result["l2_flagged"]      = l2_flag
        result["l2_decision_src"] = decision_source

        # Resolve category from L2 before entering L3
        # L3 uses this regardless of what it decides
        category, cat_source, cat_conf = self.layer2_category_lr(X, bert_res)
        result["layer2_cat"] = {
            "category": category,
            "source"  : cat_source,
            "conf"    : cat_conf,
        }

        # ── Layer 3 — final gate ──────────────────────────────────
        # Compulsory when L1+L2 both passed (no early block from either)
        harmful_res = self.layer3_harmful(text)
        result["layer3"] = harmful_res

        harmful_flagged = (
            harmful_res is not None
            and harmful_res["malicious"]
            and harmful_res["confidence"] >= self.HARMFUL_CONF_THRESHOLD
        )

        if l2_flag or harmful_flagged:
            # Determine precise block attribution
            if l2_flag and harmful_flagged:
                blocked_at = "Layer 2+3 (BERT + Harmful Detector)"
            elif l2_flag:
                blocked_at = "Layer 2 (BERT-BiLSTM)"
            else:
                blocked_at = "Layer 3 (Harmful Detector)"

            # Category from L2 resolution; fallback label if benign-tagged
            final_category = category if category.lower() != "benign" else "harmful_content"

            result["malicious"]       = True
            result["blocked_at"]      = blocked_at
            result["decision_source"] = decision_source
            result["category"]        = final_category
            return result

        # ── All layers passed → ALLOW ─────────────────────────────
        result["decision_source"] = "ALL_LAYERS_PASSED"
        return result


# -----------------------------------------------------------------
# MULTILAYER DEFENSE NODE (Our project's interface)
# -----------------------------------------------------------------
class MultilayerDefenseNode(BaseAdversarialNode):
    def __init__(self, config: Dict[str, Any]):
        # BaseAdversarialNode expects config, which might contain name and node_configs
        super().__init__(config=config)
        
        # Extract name and node_configs if they are part of the config
        self.name = config.get('name', self.__class__.__name__)
        self.node_configs = config.get('node_configs', {})
        
        self.defense_system: Optional[DefenseSystem] = None
        self.initialize_defense_system()

    def initialize_defense_system(self):
        """Initializes the DefenseSystem with models from the nodes/data directory."""
        print(f"🔄  Initializing Multilayer Defense System for node: {self.name}...")

        # Check if essential Layer 1 models exist
        missing_l1_models = []
        if not VECTORIZER_PATH.exists(): missing_l1_models.append(f"vectorizer.pkl (expected at {VECTORIZER_PATH})")
        if not CATEGORY_LR_PATH.exists(): missing_l1_models.append(f"category_model.pkl (expected at {CATEGORY_LR_PATH})")
        if not CATEGORY_LE_PATH.exists(): missing_l1_models.append(f"label_encoder.pkl (expected at {CATEGORY_LE_PATH})")
        for name, p in BINARY_MODELS.items():
            if not p.exists():
                missing_l1_models.append(f"{str(p.name)} (expected at {p})")

        if missing_l1_models:
            print(f"  ⚠️  Missing Layer 1 models: {'; '.join(missing_l1_models)}. Layer 1 defense may be unavailable.")
        
        # BERT models check
        missing_bert_models = []
        if not BERT_CKPT_PATH.exists(): missing_bert_models.append(f"BERT checkpoint (expected at {BERT_CKPT_PATH})")
        if not BERT_LE_PATH.exists(): missing_bert_models.append(f"BERT label encoder (expected at {BERT_LE_PATH})")
        if missing_bert_models:
            print(f"  ⚠️  Missing BERT models: {'; '.join(missing_bert_models)}. BERT-BiLSTM defense may be unavailable.")

        # Harmful Detector models check
        missing_harmful_detector = []
        if not HARMFUL_DETECTOR_DIR.exists(): missing_harmful_detector.append(f"Harmful Detector directory (expected at {HARMFUL_DETECTOR_DIR})")
        if missing_harmful_detector:
            print(f"  ⚠️  Missing Harmful Detector: {'; '.join(missing_harmful_detector)}. Harmful Content Detector defense may be unavailable.")


        try:
            self.defense_system = DefenseSystem(
                binary_models_paths = BINARY_MODELS,
                vectorizer_path = VECTORIZER_PATH,
                category_lr_path = CATEGORY_LR_PATH,
                category_le_path = CATEGORY_LE_PATH,
                bert_ckpt_path = BERT_CKPT_PATH,
                bert_le_path = BERT_LE_PATH,
                harmful_detector_dir = HARMFUL_DETECTOR_DIR,
                ensemble_vote_threshold = ENSEMBLE_VOTE_THRESHOLD,
                bert_override_conf = BERT_OVERRIDE_CONF,
                bert_medium_conf = BERT_MEDIUM_CONF,
                bert_category_conf = BERT_CATEGORY_CONF,
                harmful_conf_threshold = HARMFUL_CONF_THRESHOLD,
                device = DEVICE
            )
            print(f"✅  Multilayer Defense System for {self.name} ready.\n")

        except Exception as e:
            print(f"❌  An error occurred during DefenseSystem initialization for {self.name}: {e}")
            self.defense_system = None # Ensure it's None if initialization fails

    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Processes the input data through the multilayer defense pipeline.
        Retrieves input from state and returns updated state.
        """
        if runtime_config is None:
            runtime_config = {}
        if self.defense_system is None:
            print(f"Error: Defense System not initialized for node {self.name}. Cannot process input.")
            return {"defence": {"error": "Defense system not initialized"}, "node_name": self.name, "routing_signal": RoutingSignals.CONTINUE}
            
        print(f"🚀 Executing Multilayer Defense node: {self.name}")
        
        # --- Retrieve input data from state ---
        input_prompt = None
        prompt_key_attempts = ['input_prompt', 'prompt', 'text', 'attack_prompt'] # Common keys for input prompt

        # Try to get from payload first
        if 'payload' in state and isinstance(state['payload'], dict):
            for key in prompt_key_attempts:
                if key in state['payload'] and isinstance(state['payload'][key], str):
                    input_prompt = state['payload'][key]
                    print(f"  Found input prompt in state['payload']['{key}']")
                    break

        # Fallback to current_turn if not found in payload
        if input_prompt is None and 'current_turn' in state and isinstance(state['current_turn'], dict):
            turn_data = state['current_turn']
            if 'attack' in turn_data and isinstance(turn_data['attack'], (str, dict)):
                # If 'attack' is a dict, assume it has a 'text' or 'prompt' field
                if isinstance(turn_data['attack'], str):
                    input_prompt = turn_data['attack']
                elif isinstance(turn_data['attack'], dict) and 'prompt' in turn_data['attack']:
                    input_prompt = turn_data['attack']['prompt']
                elif isinstance(turn_data['attack'], dict) and 'text' in turn_data['attack']:
                    input_prompt = turn_data['attack']['text']
                print(f"  Found input prompt in state['current_turn']['attack']")
            elif 'defence' in turn_data and isinstance(turn_data['defence'], (str, dict)):
                 if isinstance(turn_data['defence'], str):
                    input_prompt = turn_data['defence']
                 elif isinstance(turn_data['defence'], dict) and 'prompt' in turn_data['defence']:
                    input_prompt = turn_data['defence']['prompt']
                 elif isinstance(turn_data['defence'], dict) and 'text' in turn_data['defence']:
                    input_prompt = turn_data['defence']['text']
                 print(f"  Found input prompt in state['current_turn']['defence']")

        if input_prompt is None:
            print("Warning: Could not find input prompt in state. Using empty string for defense.")
            input_prompt = "" # Use empty string if no prompt is found

        # Ensure input_prompt is a string for prediction
        if not isinstance(input_prompt, str):
            print(f"Warning: Input prompt is not a string (type: {type(input_prompt)}). Attempting conversion to string.")
            try:
                input_prompt = str(input_prompt)
            except Exception as e:
                print(f"Error converting input prompt to string: {e}")
                return {"defence": {"error": f"Invalid input type, conversion failed: {e}"}, "node_name": self.name, "routing_signal": RoutingSignals.CONTINUE}

        try:
            # Use the predict method from the loaded DefenseSystem
            result = self.defense_system.predict(input_prompt)
            print("✅ Defense pipeline executed successfully.")
            
            # --- Update state with results ---
            # The node should return a dictionary that updates specific fields in the SystemState.
            # We're updating the 'defence' field within 'current_turn'.
            return {
                "current_turn": TurnData(
                    defence=result, # The full result of the defense system
                    node_name=self.name, # Record which node executed
                    timestamp=datetime.utcnow().isoformat() # Update timestamp
                ),
                "routing_signal": RoutingSignals.CONTINUE # Continue to the next node in the graph
            }

        except Exception as e:
            print(f"❌ Error during defense system prediction for node {self.name}: {e}")
            return {"defence": {"error": f"Defense system failed: {e}"}, "node_name": self.name, "routing_signal": RoutingSignals.CONTINUE}

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        """Return JSON schema for node parameters"""
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name identifier for this defense node",
                    "default": "multilayer_defense"
                },
                "node_configs": {
                    "type": "object",
                    "description": "Configuration for individual node components"
                }
            }
        }

