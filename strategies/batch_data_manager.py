"""
================================================================================
BATCH DATA MANAGER
================================================================================

Responsible for persisting and loading batch prompt datasets to/from disk.

WHY THIS EXISTS:
    The UI uploads the prompts file as a base64-encoded blob inside strategy_params.
    Storing that blob in MongoDB would be wasteful (potentially MBs per run) and
    would bloat every run document fetched by the frontend.

    Instead, on run creation we:
      1. Decode the base64 blob
      2. Parse and validate the JSON
      3. Save the prompts list to:  strategies/data/batch/<run_id>.json
      4. Strip prompts_file + prompts_file_name from strategy_params
      5. Replace them with prompts_file_path (relative path) in strategy_params

    On strategy initialization (BatchStrategy._load_dataset), we simply read
    the file from disk. No blob in memory, no blob in the DB.

STORAGE LOCATION:
    strategies/data/batch/<run_id>.json

    Stored as a plain JSON list of strings:
        ["prompt 1", "prompt 2", ...]

    This keeps the file simple and easy to inspect/debug manually.
================================================================================
"""

import base64
import json
import os
from pathlib import Path
from typing import List, Optional

from core.logging import step, warn, err

# Canonical storage directory — relative to project root
BATCH_DATA_DIR = Path(__file__).parent / "data" / "batch"


def get_batch_data_dir() -> Path:
    """Return the batch data directory, creating it if it doesn't exist."""
    BATCH_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return BATCH_DATA_DIR


def save_prompts_for_run(run_id: str, prompts: List[str]) -> str:
    """
    Save a list of prompts to disk for a given run.

    Args:
        run_id:   The run identifier (used as the filename).
        prompts:  Validated list of prompt strings.

    Returns:
        Relative path string stored in strategy_params["prompts_file_path"].
        Relative to the project root so it works regardless of CWD.
    """
    data_dir = get_batch_data_dir()
    file_path = data_dir / f"{run_id}.json"

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, ensure_ascii=False, indent=2)

    # Store a path relative to the strategies directory so it's portable
    relative_path = str(file_path.relative_to(Path(__file__).parent.parent))
    step("Batch prompts saved to disk", run_id=run_id, path=relative_path, count=len(prompts))
    return relative_path


def load_prompts_for_run(prompts_file_path: str) -> Optional[List[str]]:
    """
    Load prompts from disk given the relative path stored in strategy_params.

    The path is resolved relative to the project root (parent of the
    strategies/ directory).

    Args:
        prompts_file_path: Relative path as stored in strategy_params.

    Returns:
        List of prompt strings, or None if the file is missing/invalid.
    """
    # Resolve relative to project root (parent of strategies/)
    project_root = Path(__file__).parent.parent
    resolved = project_root / prompts_file_path

    if not resolved.exists():
        err("Batch prompts file not found on disk", path=str(resolved))
        return None

    try:
        with open(resolved, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            err("Batch prompts file is not a JSON list", path=str(resolved))
            return None

        prompts = [str(p) for p in data]
        step("Batch prompts loaded from disk", path=str(resolved), count=len(prompts))
        return prompts

    except Exception as e:
        err("Failed to read batch prompts file", path=str(resolved), error=str(e))
        return None


def delete_prompts_for_run(run_id: str) -> bool:
    """
    Delete the prompts file for a run (e.g. when the run is deleted).

    Args:
        run_id: The run identifier.

    Returns:
        True if deleted, False if file didn't exist.
    """
    data_dir = get_batch_data_dir()
    file_path = data_dir / f"{run_id}.json"

    if file_path.exists():
        file_path.unlink()
        step("Batch prompts file deleted", run_id=run_id)
        return True

    warn("Batch prompts file not found for deletion", run_id=run_id)
    return False


def decode_and_validate_prompts_file(
    b64_content: str,
    file_name: str = "unknown",
) -> List[str]:
    """
    Decode a base64-encoded JSON file and return a validated list of prompts.

    Accepted JSON formats:
        - Plain list:   ["p1", "p2", ...]
        - Keyed object: {"prompts": ["p1", "p2", ...]}

    Raises:
        ValueError: If the content cannot be decoded, parsed, or validated.
    """
    try:
        decoded_bytes = base64.b64decode(b64_content)
    except Exception as e:
        raise ValueError(f"Invalid base64 encoding in '{file_name}': {e}") from e

    try:
        decoded_str = decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"File '{file_name}' is not valid UTF-8: {e}") from e

    try:
        data = json.loads(decoded_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"File '{file_name}' is not valid JSON: {e}") from e

    if isinstance(data, list):
        prompts = [str(p) for p in data]
    elif isinstance(data, dict) and "prompts" in data:
        prompts = [str(p) for p in data["prompts"]]
    else:
        raise ValueError(
            f"File '{file_name}' must be a JSON list or {{\"prompts\": [...]}}. "
            f"Got: {type(data).__name__}"
        )

    if not prompts:
        raise ValueError(f"File '{file_name}' contains an empty prompts list.")

    return prompts
