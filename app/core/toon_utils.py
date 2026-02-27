"""TOON format utilities — compact LLM-friendly serialization via toonify.

TOON reduces structured data token usage by 30–60% by hoisting shared
keys/schema once and emitting rows of values.  This module provides:

  - toon_encode(data)   → compact TOON string (or plain str on failure)
  - toon_decode(text)   → Python dict/list
  - toon_safe(data)     → encode if structured, pass-through if plain string
  - toon_context(dict)  → encode GNOME desktop context for chat injection

Use toon_safe() whenever you're not sure if data is already a string.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import toonify; fall back gracefully if not installed
try:
    from toon import encode as _toon_encode, decode as _toon_decode
    _TOON_AVAILABLE = True
    logger.debug("toonify loaded — TOON compression enabled")
except ImportError:
    _TOON_AVAILABLE = False
    logger.warning(
        "toonify not installed — TOON compression disabled. "
        "Run: pip install toonify"
    )


def is_available() -> bool:
    """Return True if toonify is installed and TOON encoding is available."""
    return _TOON_AVAILABLE


def toon_encode(data: Any) -> str:
    """Serialize Python data to TOON format.

    Args:
        data: Any JSON-serialisable Python object (dict, list, etc.).

    Returns:
        TOON-encoded string, or JSON string if toonify is unavailable.

    Raises:
        Never raises — falls back to json.dumps on any error.
    """
    if not _TOON_AVAILABLE:
        return json.dumps(data, ensure_ascii=False)
    try:
        return _toon_encode(data)
    except Exception as e:
        logger.debug("TOON encode failed (%s), falling back to JSON", e)
        return json.dumps(data, ensure_ascii=False)


def toon_decode(text: str) -> Any:
    """Deserialize a TOON string back to Python data.

    Args:
        text: TOON-encoded string.

    Returns:
        Decoded Python object.

    Raises:
        ValueError: if neither TOON nor JSON can parse the string.
    """
    if not _TOON_AVAILABLE:
        return json.loads(text)
    try:
        return _toon_decode(text)
    except Exception:
        # Falls back to JSON (useful if text was stored as JSON)
        return json.loads(text)


def toon_safe(data: Any) -> str:
    """Encode data to TOON if it is structured; return as-is if already a string.

    This is the main helper for tool outputs — if an MCP tool returns a plain
    string that's already human-readable, we leave it alone.  If it returns a
    dict or list, we TOON-encode it for the LLM.

    Args:
        data: Tool output — str, dict, list, or anything JSON-serialisable.

    Returns:
        TOON string (for dicts/lists) or plain string (for str/int/float).
    """
    if isinstance(data, str):
        # Already a string — attempt to parse as JSON and re-encode as TOON
        # only if it's actually structured (starts with { or [)
        stripped = data.strip()
        if stripped and stripped[0] in ("{", "["):
            try:
                parsed = json.loads(stripped)
                return toon_encode(parsed)
            except (json.JSONDecodeError, ValueError):
                pass
        return data

    if isinstance(data, (dict, list)):
        return toon_encode(data)

    return str(data)


def toon_context(context: dict[str, Any]) -> str:
    """Compact-encode GNOME desktop context for chat system message injection.

    Produces a TOON representation like:
        context{active_app,path,clipboard}: Firefox,~/Documents,Hello world

    Args:
        context: Dict with optional keys: active_app, current_path, clipboard.

    Returns:
        TOON string if toonify available, else formatted key=value lines.
    """
    # Filter out None/empty values
    filtered = {k: v for k, v in context.items() if v}
    if not filtered:
        return ""

    if _TOON_AVAILABLE:
        try:
            return _toon_encode(filtered)
        except Exception:
            pass

    # Fallback: plain key=value pairs
    return "\n".join(f"{k}: {v}" for k, v in filtered.items())
