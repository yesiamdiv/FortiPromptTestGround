import inspect
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# ─────────────────────────────────────────────────────────────
# CONFIG  (driven by core.env / environment variables)
# ─────────────────────────────────────────────────────────────

# Lazy import avoids circular dependencies; settings are read once on first use.
def _load_debug_config() -> tuple[bool, int]:
    try:
        from core.env import get_settings
        s = get_settings()
        enabled = s.debug_enabled
        level_name = s.log_level.lower()
    except Exception:
        # Fallback if settings are unavailable during early startup
        enabled = False
        level_name = "warning"
    levels = {"trace": 10, "debug": 20, "info": 30, "warning": 40, "error": 50, "critical": 60}
    return enabled, levels.get(level_name, 40)


DEBUG_ENABLED, MIN_LOG_LEVEL = _load_debug_config()

LOG_LEVELS = {
    "trace": 10,
    "debug": 20,
    "info": 30,
    "warning": 40,
    "error": 50,
    "critical": 60,
}

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

COLORS = {
    "debug": "\033[36m",
    "info": "\033[32m",
    "warning": "\033[33m",
    "error": "\033[31m",
    "critical": "\033[35m",
    "trace": "\033[34m",
    "cyan": "\033[96m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "magenta": "\033[95m",
}

LEVEL_LABELS = {
    "DEBUG": "DEBUG",
    "INFO": "INFO ",
    "WARNING": "WARN ",
    "ERROR": "ERROR",
    "CRITICAL": "CRIT ",
    "TRACE": "TRACE",
}

# core/logging.py lives two levels below the repo root (core/logging.py → core/ → root)
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
except Exception:
    PROJECT_ROOT = Path.cwd()


# ─────────────────────────────────────────────────────────────
# INTERNALS
# ─────────────────────────────────────────────────────────────

def _enable_windows_ansi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        kernel32.SetConsoleMode(handle, 7)
    except Exception:
        pass


def _get_caller_info(skip: int = 2) -> tuple[str, str, int]:
    """Get caller info skipping internal frames."""
    frame = inspect.currentframe()
    try:
        for _ in range(skip):
            if frame is None:
                break
            frame = frame.f_back

        if frame is None:
            return "unknown", "unknown", 0

        code = frame.f_code
        return code.co_name, code.co_filename, frame.f_lineno
    finally:
        del frame  # prevent reference cycles


def _format_path(path: str) -> str:
    """Return project-relative path if possible."""
    try:
        p = Path(path).resolve()
        rel = p.relative_to(PROJECT_ROOT)
        return rel.as_posix()
    except Exception:
        return Path(path).name


def _resolve_color(color: Optional[str], level: str) -> str:
    if color:
        return COLORS.get(color, color)
    return COLORS.get(level, COLORS["debug"])


# ─────────────────────────────────────────────────────────────
# CORE LOGGER
# ─────────────────────────────────────────────────────────────

def debug(
    message: str,
    level: str = "debug",
    color: Optional[str] = None,
    show_caller: bool = True,
    **kwargs: Any
) -> None:

    if not DEBUG_ENABLED:
        return

    if LOG_LEVELS.get(level.lower(), 0) < MIN_LOG_LEVEL:
        return

    _enable_windows_ansi()

    func_name, filename, lineno = (
        _get_caller_info() if show_caller else ("", "", 0)
    )

    c = _resolve_color(color, level)
    level_label = LEVEL_LABELS.get(level.upper(), "DEBUG")
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

    parts = [
        f"{DIM}{ts}{RESET}",
        f"{BOLD}{c}{level_label}{RESET}",
        f"{DIM}{_format_path(filename)}:{lineno}{RESET}",
    ]

    if show_caller and func_name:
        parts.append(f"{BOLD}{COLORS['cyan']}{func_name}(){RESET}")

    header = "  ".join(parts)

    print(header)
    print(f"  {COLORS['cyan']}|{RESET} {message}")

    for k, v in kwargs.items():
        print(f"  {DIM}| {k}:{RESET} {v}")


# ─────────────────────────────────────────────────────────────
# CONVENIENCE WRAPPERS
# ─────────────────────────────────────────────────────────────

def tracer(message: str = "", **kwargs: Any) -> None:
    debug(message, level="trace", **kwargs)


def step(message: str, **kwargs: Any) -> None:
    debug(message, level="info", color="green", **kwargs)


def checkpoint(message: str, **kwargs: Any) -> None:
    debug(message, level="info", color="magenta", **kwargs)


def warn(message: str, **kwargs: Any) -> None:
    debug(message, level="warning", **kwargs)


def err(message: str, **kwargs: Any) -> None:
    debug(message, level="error", **kwargs)


def state(data: dict, label: str = "state") -> None:
    debug(f"[{label}]", level="debug", show_caller=False)
    for k, v in data.items():
        print(f"  {DIM}|{RESET} {k}: {v}")
