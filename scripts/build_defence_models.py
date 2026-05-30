"""
PromptShield — Cascading Heterogeneous Defense Pipeline (CLI)
=============================================================

Research Motivation
───────────────────
Traditional LLM guards rely on static rule-based filters (keyword lists, regex
patterns). These are brittle — easily bypassed by paraphrasing, leet-speak, or
indirect phrasing. PromptShield replaces this with three learned layers, each
covering the blind spots of the previous.

Architecture
────────────
Layer 1 │ Ensemble ML (BoW+LR, BoW+GB, TF-IDF+RF)
        │   Replaces static rule-based guards. Fast, lightweight baseline.
        │   Majority vote (≥2/3). If blocked → STOP, skip L2/L3.
        ▼
Layer 2 │ BERT-BiLSTM + Category LR  [majority brain]
        │   Deep contextual understanding. Catches prompt injection,
        │   jailbreaks, role hijacking, indirect/multi-turn attacks.
        │   Known weakness: trained on injection taxonomy → misses harmful
        │   intent phrased as benign questions ("how to kill my brother").
        │   Category LR supports BERT when BERT is low-confidence.
        │   L2 does NOT block on its own — flags and passes to L3.
        ▼
Layer 3 │ Harmful Content Detector  [final gate]
        │   Only reached when L1+L2 both passed without blocking.
        │   Catches harmful intent that slips past L2 — violence, weapons,
        │   self-harm, abuse — including obfuscated forms (k!ll, b0mb).
        │   Blocks if: L2 flagged OR harmful detector confirms.
        │   Category always sourced from L2 (BERT primary, LR fallback).
        ▼
        ALLOWED ✅

Usage
─────
    python defense_pipeline.py                   # interactive
    python defense_pipeline.py --text "..."      # single prompt
    python defense_pipeline.py --batch file.txt  # one prompt per line
"""

import argparse
import sys
import torch
import torch.nn as nn
import joblib
from pathlib import Path
from transformers import (
    BertTokenizer, BertModel,
    AutoTokenizer, AutoModelForSequenceClassification,
)

# ─────────────────────────────────────────────────────────────────
# CONFIG  ← edit paths here
# ─────────────────────────────────────────────────────────────────
MODEL_DIR = Path(".")

BINARY_MODELS = {
    "BoW+LR"   : MODEL_DIR / "BoW__Logistic_Regression.joblib",
    "BoW+GB"   : MODEL_DIR / "BoW__Gradient_Boosting.joblib",
    "TF-IDF+RF": MODEL_DIR / "TF-IDF__Random_Forest.joblib",
}
VECTORIZER_PATH  = MODEL_DIR / "vectorizer.pkl"
CATEGORY_LR_PATH = MODEL_DIR / "category_model.pkl"
CATEGORY_LE_PATH = MODEL_DIR / "label_encoder.pkl"

BERT_CKPT_PATH = Path(r"D:\Users\ASUS\Downloads\fortiprompt_bert_rnn.pt")
BERT_LE_PATH   = Path(r"D:\Users\ASUS\Downloads\label_encoder.pkl")

HARMFUL_DETECTOR_DIR  = Path(r"C:\Users\ASUS\OneDrive\Desktop\model test\fortiprompt_harmful_detector")
HARMFUL_LABEL_MAP     = {0: "BENIGN", 1: "MALICIOUS"}   # CLASS_1 = malicious (confirmed)
HARMFUL_MALICIOUS_IDS = {1}

# Decision thresholds
ENSEMBLE_VOTE_THRESHOLD = 2     # votes needed out of 3 to flag
BERT_OVERRIDE_CONF      = 0.85  # BERT treated as high-confidence above this
BERT_MEDIUM_CONF        = 0.60  # BERT flag accepted at medium confidence
BERT_CATEGORY_CONF      = 0.80  # use BERT category above this, else LR
HARMFUL_CONF_THRESHOLD  = 0.75  # harmful detector blocks above this

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ─────────────────────────────────────────────────────────────────
# BERT-RNN MODEL DEFINITION
# ─────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────
# DEFENSE SYSTEM
# ─────────────────────────────────────────────────────────────────
class DefenseSystem:
    def __init__(self):
        print("🔄  Loading models...")

        # L1 deps
        self.vectorizer       = joblib.load(VECTORIZER_PATH)
        self.category_lr      = joblib.load(CATEGORY_LR_PATH)
        self.label_encoder_lr = joblib.load(CATEGORY_LE_PATH)
        self.binary_models    = {n: joblib.load(p) for n, p in BINARY_MODELS.items()}
        print(f"  ✅ [L1] Ensemble models  loaded  ({list(self.binary_models.keys())})")

        # L2 — BERT-BiLSTM
        self.bert_model         = None
        self.bert_tokenizer     = None
        self.label_encoder_bert = None
        self.bert_available     = False

        if BERT_CKPT_PATH.exists() and BERT_LE_PATH.exists():
            try:
                ckpt = torch.load(str(BERT_CKPT_PATH), map_location=DEVICE)
                cfg  = ckpt["config"]
                self.bert_model = BertRNNClassifier(
                    model_name    = cfg["model_name"],
                    num_classes   = ckpt["num_classes"],
                    rnn_type      = cfg["rnn_type"],
                    hidden_size   = cfg["hidden_size"],
                    num_layers    = cfg["num_layers"],
                    bidirectional = cfg["bidirectional"],
                    dropout       = cfg["rnn_dropout"],
                ).to(DEVICE)
                self.bert_model.load_state_dict(ckpt["model_state_dict"])
                self.bert_model.eval()
                self.bert_tokenizer     = BertTokenizer.from_pretrained(cfg["model_name"])
                self.label_encoder_bert = joblib.load(str(BERT_LE_PATH))
                self.bert_available     = True
                print(f"  ✅ [L2] BERT-BiLSTM      loaded  | classes: {list(self.label_encoder_bert.classes_)}")
            except Exception as e:
                print(f"  ⚠️  [L2] BERT-BiLSTM failed: {e} → LR-only mode")
        else:
            print(f"  ⚠️  [L2] BERT checkpoint not found → LR-only mode")

        # L3 — Harmful Content Detector
        self.harmful_tokenizer = None
        self.harmful_model     = None
        self.harmful_available = False

        if HARMFUL_DETECTOR_DIR.exists():
            try:
                self.harmful_tokenizer = AutoTokenizer.from_pretrained(str(HARMFUL_DETECTOR_DIR))
                self.harmful_model     = AutoModelForSequenceClassification.from_pretrained(
                                             str(HARMFUL_DETECTOR_DIR)).to(DEVICE)
                self.harmful_model.eval()
                self.harmful_available = True
                print(f"  ✅ [L3] Harmful Detector loaded  ({HARMFUL_DETECTOR_DIR.name})")
            except Exception as e:
                print(f"  ⚠️  [L3] Harmful Detector failed: {e}")
        else:
            print(f"  ⚠️  [L3] Harmful Detector not found at {HARMFUL_DETECTOR_DIR}")

        print(f"\n  🖥️  Device : {DEVICE}")
        print(f"  🛡️  Layers : L1=Ensemble → L2=BERT+LR → L3=HarmfulDetector [final gate]")
        print(f"✅  System ready.\n")

    # ── Layer 1: Ensemble ML ──────────────────────────────────────
    def layer1_ensemble(self, text):
        from sklearn.pipeline import Pipeline
        clean = text.lower().strip()
        X     = self.vectorizer.transform([clean])
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

        votes    = sum(r["pred"] for r in preds)
        flag     = 1 if votes >= ENSEMBLE_VOTE_THRESHOLD else 0
        avg_conf = sum(r["conf"] for r in preds) / len(preds)
        return flag, avg_conf, preds, X

    # ── Layer 2: BERT-BiLSTM ──────────────────────────────────────
    def layer2_bert(self, text):
        if not self.bert_available:
            return None

        inputs = self.bert_tokenizer(
            text, return_tensors="pt", truncation=True,
            padding=True, max_length=128,
        ).to(DEVICE)

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
        lr_probs = self.category_lr.predict_proba(X)[0]
        lr_idx   = lr_probs.argmax()
        lr_cat   = self.label_encoder_lr.inverse_transform([lr_idx])[0]
        lr_conf  = float(lr_probs[lr_idx])

        if bert_res and bert_res["confidence"] >= BERT_CATEGORY_CONF:
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
        ).to(DEVICE)

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
        decision_source = "ENSEMBLE_ONLY"

        if bert_res:
            if bert_res["confidence"] >= BERT_OVERRIDE_CONF:
                l2_flag         = bool(bert_res["malicious"])
                decision_source = "BERT"
            elif bert_res["confidence"] >= BERT_MEDIUM_CONF:
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
            and harmful_res["confidence"] >= HARMFUL_CONF_THRESHOLD
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


# ─────────────────────────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────────────────────────
W = 64

def print_result(res, idx=None):

    label = f"Prompt #{idx}" if idx is not None else "Prompt"
    short = res["text"][:55] + "..." if len(res["text"]) > 55 else res["text"]

    print(f"\n{'═'*W}")
    print(f"  {label}: {short}")
    print(f"{'─'*W}")

    # ── Layer 1 ──────────────────────────────────────────────────
    l1 = res["layer1"]
    print("  [LAYER 1]  Ensemble ML  (replaces rule-based guards)")
    for m in l1["models"]:
        icon    = "🚩" if m["pred"] else "✅"
        verdict = "MALICIOUS" if m["pred"] else "benign"
        print(f"    {m['name']:<14}  {icon} {verdict:<10}  conf={m['conf']:.3f}")
    l1_status = "🚩 FLAGGED → BLOCKED" if l1["flag"] else "✅ PASSED → L2"
    print(f"    {'Ensemble':<14}  {l1_status}   avg_conf={l1['avg_conf']:.3f}")

    if res["blocked_at"] == "Layer 1 (Ensemble ML)":
        # Show L2 category resolution if available
        if res.get("layer2_cat"):
            c = res["layer2_cat"]
            print(f"  [LAYER 2]  Category Resolution (post-L1 block)")
            print(f"    Category src    {c['source']} → {c['category']}  (conf={c['conf']:.3f})")
        _print_verdict(res)
        return

    # ── Layer 2 ──────────────────────────────────────────────────
    print("  [LAYER 2]  BERT-BiLSTM + Category LR  (contextual)")
    if res["layer2"]:
        b       = res["layer2"]
        icon    = "🚩" if b["malicious"] else "✅"
        verdict = "MALICIOUS" if b["malicious"] else "benign"
        l2_status = "FLAGGED → passed to L3" if res["l2_flagged"] else "PASSED → L3"
        print(f"    BERT Decision   {icon} {verdict:<10}  conf={b['confidence']:.3f}")
        print(f"    BERT Status     {l2_status}")
        print(f"    BERT Category   {b['category']}")
        top3     = sorted(b["all_probs"].items(), key=lambda x: -x[1])[:3]
        top3_str = "  ".join(f"{k}={v:.3f}" for k, v in top3)
        print(f"    Top-3 probs     {top3_str}")
    else:
        print("    ⚠️  BERT not available — skipped")

    if res["layer2_cat"]:
        c = res["layer2_cat"]
        print(f"    Category src    {c['source']} → {c['category']}  (conf={c['conf']:.3f})")

    # ── Layer 3 ──────────────────────────────────────────────────
    print("  [LAYER 3]  Harmful Content Detector  [final gate]")
    if res["layer3"]:
        h       = res["layer3"]
        icon    = "🚩" if h["malicious"] else "✅"
        verdict = "HARMFUL" if h["malicious"] else "benign"
        print(f"    Decision        {icon} {verdict:<10}  conf={h['confidence']:.3f}")
        scores_str = "  ".join(f"{k}={v:.3f}" for k, v in h["all_scores"].items())
        print(f"    Scores          {scores_str}")
    else:
        print("    ⚠️  Harmful Detector not available — skipped")

    _print_verdict(res)


def _print_verdict(res):
    print(f"{'─'*W}")
    if res["malicious"]:
        print(f"  🔴 VERDICT      : BLOCKED")
        print(f"  🛑 Blocked at   : {res['blocked_at']}")
        print(f"  🏷️  Category     : {res['category']}")
        print(f"  ℹ️  Decided by   : {res['decision_source']}")
    else:
        print(f"  🟢 VERDICT      : ALLOWED  (passed all 3 layers)")
        print(f"  ℹ️  Decision     : {res['decision_source']}")
    print(f"{'═'*W}")


def print_batch_summary(results):
    blocked = [r for r in results if r["malicious"]]
    allowed = [r for r in results if not r["malicious"]]

    layer_counts = {}
    for r in blocked:
        key = r["blocked_at"] or "Unknown"
        layer_counts[key] = layer_counts.get(key, 0) + 1

    cat_counts = {}
    for r in blocked:
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1

    print(f"\n{'═'*W}")
    print("  BATCH SUMMARY")
    print(f"{'─'*W}")
    print(f"  Total    : {len(results)}")
    print(f"  Blocked  : {len(blocked)}  🔴")
    print(f"  Allowed  : {len(allowed)}  🟢")

    if layer_counts:
        print(f"\n  Blocked by layer:")
        for layer, count in sorted(layer_counts.items()):
            bar = "█" * count
            print(f"    {layer:<36}  {count:>3}  {bar}")

    if cat_counts:
        print(f"\n  Attack categories:")
        for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
            print(f"    {cat:<32}  {count:>3}")

    if blocked:
        print(f"\n  Blocked prompts:")
        for r in blocked:
            short = r["text"][:48] + "..." if len(r["text"]) > 48 else r["text"]
            print(f"    🛑 [{r['blocked_at']}]")
            print(f"       Category : {r['category']}")
            print(f"       Prompt   : {short}")

    print(f"{'═'*W}")


# ─────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="PromptShield — Cascading 3-Layer Prompt Injection Defense"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--text",  type=str, help="Single prompt to evaluate")
    group.add_argument("--batch", type=str, help="Path to .txt file (one prompt per line)")
    args = parser.parse_args()

    system = DefenseSystem()

    if args.text:
        print_result(system.predict(args.text))
        return

    if args.batch:
        path = Path(args.batch)
        if not path.exists():
            print(f"❌ File not found: {path}")
            sys.exit(1)
        prompts = [l.strip() for l in path.read_text().splitlines() if l.strip()]
        results = []
        for i, p in enumerate(prompts, 1):
            res = system.predict(p)
            print_result(res, idx=i)
            results.append(res)
        print_batch_summary(results)
        return

    # Interactive
    print("PromptShield Interactive Mode  |  type 'exit' to quit\n")
    history = []
    while True:
        try:
            text = input("Enter prompt: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if not text:
            continue
        if text.lower() in ("exit", "quit"):
            break
        res = system.predict(text)
        print_result(res)
        history.append(res)

    if history:
        print_batch_summary(history)


if __name__ == "__main__":
    main()