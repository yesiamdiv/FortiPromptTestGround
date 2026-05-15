"""
telemetry/tracker.py

SQLite-backed Telemetry Ledger.

Logs every completed turn to a local SQLite database so you can analyse
results, compare strategies, track breach rates, etc.

Schema:
    table: run_log
        id              INTEGER PRIMARY KEY
        timestamp       TEXT
        run_id          TEXT
        strategy        TEXT
        turn_count      INTEGER
        goal            TEXT
        current_prompt  TEXT
        current_response TEXT
        evaluation_result TEXT
        evaluation_reasoning TEXT
        final_outcome   TEXT
        strategy_metadata TEXT  (JSON blob)
"""

import json
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = "logs/run_history.sqlite3"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS run_log (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp            TEXT NOT NULL,
    run_id               TEXT,
    strategy             TEXT,
    turn_count           INTEGER,
    goal                 TEXT,
    current_prompt       TEXT,
    current_response     TEXT,
    evaluation_result    TEXT,
    evaluation_reasoning TEXT,
    final_outcome        TEXT,
    strategy_metadata    TEXT
);
"""


class SQLiteTracker:
    """
    Logs run state to a SQLite database after every completed turn.

    Args:
        db_path: Path to the SQLite database file.
                 Will be created (along with parent dirs) if it doesn't exist.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()
        return conn

    def log(self, state: dict, outcome: str) -> None:
        """Persist the current state to the database."""
        try:
            conn = self._get_connection()
            conn.execute(
                """
                INSERT INTO run_log (
                    timestamp, run_id, strategy, turn_count, goal,
                    current_prompt, current_response,
                    evaluation_result, evaluation_reasoning,
                    final_outcome, strategy_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    state.get("run_id", ""),
                    state.get("strategy", ""),
                    state.get("turn_count", 0),
                    state.get("goal", ""),
                    state.get("current_prompt", ""),
                    state.get("current_response", ""),
                    state.get("evaluation_result", ""),
                    state.get("evaluation_reasoning", ""),
                    outcome,
                    json.dumps(state.get("strategy_metadata", {})),
                ),
            )
            conn.commit()
            conn.close()
            logger.debug(f"Telemetry logged run_id={state.get('run_id')} turn={state.get('turn_count')}")
        except Exception as exc:
            logger.error(f"Telemetry write failed: {exc}")

    def get_all(self) -> list[dict]:
        """Retrieve all logged runs as a list of dicts."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT * FROM run_log ORDER BY id DESC")
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return rows