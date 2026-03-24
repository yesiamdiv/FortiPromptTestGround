"""
redgen/utils/output.py
───────────────────────
Save generated test cases to CSV + JSON and print a summary.
"""

import os
from datetime import datetime

import pandas as pd


def save_outputs(df: pd.DataFrame, output_dir: str, tag: str = "") -> tuple:
    os.makedirs(output_dir, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"testcases_{tag}_{ts}" if tag else f"testcases_{ts}"

    csv_path  = os.path.join(output_dir, stem + ".csv")
    json_path = os.path.join(output_dir, stem + ".json")

    df.to_csv(csv_path,  index=False)
    df.to_json(json_path, orient="records", indent=2, force_ascii=False)

    print(f"\n{'='*60}")
    print(f"[Output] CSV  → {csv_path}")
    print(f"[Output] JSON → {json_path}")
    print(f"[Output] Total test cases : {len(df)}")

    print("\n[Summary] attack_type × generation_mode:")
    summary = (
        df.groupby(["attack_type", "generation_mode"])
        .size()
        .reset_index(name="count")
    )
    print(summary.to_string(index=False))

    print("\n[Summary] language breakdown:")
    print(df["language"].value_counts().to_string())

    print("\n[Summary] encoding breakdown:")
    print(df["encoding"].value_counts().to_string())

    return csv_path, json_path
