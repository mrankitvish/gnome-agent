"""Filesystem MCP server — safe file and directory operations for the agent.

Exposed tools:
  - read_file        Read text file contents
  - write_file       Write or append to a text file
  - list_directory   List directory contents with metadata
  - search_files     Glob/regex search for files
  - file_info        Stat a file (size, mtime, permissions)
  - create_directory Create a directory tree

Safety: all paths are resolved and validated to prevent path traversal.
By default only paths under HOME and /tmp are allowed (configurable).
"""

import os
import re
import stat
from datetime import datetime
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parents[3]))

from fastmcp import FastMCP
from app.core.toon_utils import toon_encode

mcp = FastMCP("filesystem")

# ── Safety: allowed root directories ─────────────────────────────────────────
_HOME = Path.home()
_ALLOWED_ROOTS: list[Path] = [_HOME, Path("/tmp")]


def _safe_path(raw_path: str) -> Path:
    """Resolve path and validate it falls under an allowed root."""
    p = Path(raw_path).expanduser().resolve()
    for root in _ALLOWED_ROOTS:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    raise PermissionError(
        f"Path '{p}' is outside allowed directories: "
        + ", ".join(str(r) for r in _ALLOWED_ROOTS)
    )


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def read_file(path: str, max_bytes: int = 32768) -> str:
    """Read a text file and return its contents.

    Args:
        path:      Absolute or ~-relative path to the file.
        max_bytes: Maximum bytes to read (default 32 KB).

    Returns:
        File contents as a string, or an error message.
    """
    try:
        p = _safe_path(path)
        if not p.exists():
            return f"Error: file not found — {p}"
        if not p.is_file():
            return f"Error: not a file — {p}"
        size = p.stat().st_size
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_bytes)
        truncated = size > max_bytes
        header = f"# {p}  ({size:,} bytes)\n\n"
        footer = f"\n\n… [truncated — {size - max_bytes:,} bytes remaining]" if truncated else ""
        return header + content + footer
    except PermissionError as e:
        return f"Permission error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


@mcp.tool()
def write_file(path: str, content: str, append: bool = False) -> str:
    """Write content to a file.

    Args:
        path:    Path to write. Parent directories are created automatically.
        content: Text content to write.
        append:  If True, append to existing file. If False (default), overwrite.

    Returns:
        Success message with bytes written, or error.
    """
    try:
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(p, mode, encoding="utf-8") as f:
            f.write(content)
        action = "Appended" if append else "Written"
        return f"{action} {len(content.encode()):,} bytes to {p}"
    except PermissionError as e:
        return f"Permission error: {e}"
    except Exception as e:
        return f"Error writing file: {e}"


@mcp.tool()
def list_directory(path: str = "~", show_hidden: bool = False) -> str:
    """List directory contents with file sizes and modification times.

    Args:
        path:        Directory to list (default: home directory).
        show_hidden: If True, include dotfiles.

    Returns:
        Formatted directory listing.
    """
    try:
        p = _safe_path(path)
        if not p.exists():
            return f"Error: directory not found — {p}"
        if not p.is_dir():
            return f"Error: not a directory — {p}"

        entries = []
        for entry in sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
            if not show_hidden and entry.name.startswith("."):
                continue
            try:
                s = entry.stat()
                mtime = datetime.fromtimestamp(s.st_mtime).strftime("%Y-%m-%d %H:%M")
                entries.append({
                    "name": entry.name + ("/" if entry.is_dir() else ""),
                    "type": "dir" if entry.is_dir() else "file",
                    "size_bytes": s.st_size if entry.is_file() else None,
                    "modified": mtime,
                })
            except OSError:
                entries.append({"name": entry.name, "type": "unknown"})

        return toon_encode({"path": str(p), "entries": entries})
    except PermissionError as e:
        return f"Permission error: {e}"
    except Exception as e:
        return f"Error listing directory: {e}"


@mcp.tool()
def search_files(
    directory: str = "~",
    pattern: str = "*",
    use_regex: bool = False,
    max_results: int = 50,
) -> str:
    """Search for files matching a glob pattern or regex within a directory.

    Args:
        directory:   Root directory to search from.
        pattern:     Glob pattern (e.g. '*.py') or regex (if use_regex=True).
        use_regex:   If True, match filenames against a regex instead of glob.
        max_results: Maximum number of results to return.

    Returns:
        Matching paths, one per line.
    """
    try:
        root = _safe_path(directory)
        if not root.is_dir():
            return f"Error: not a directory — {root}"

        results: list[str] = []
        if use_regex:
            rx = re.compile(pattern, re.IGNORECASE)
            for p in root.rglob("*"):
                if rx.search(p.name):
                    results.append(str(p))
                    if len(results) >= max_results:
                        break
        else:
            for p in root.rglob(pattern):
                results.append(str(p))
                if len(results) >= max_results:
                    break

        if not results:
            return f"No files matching '{pattern}' found in {root}"

        return toon_encode({
            "root": str(root),
            "pattern": pattern,
            "count": len(results),
            "files": results,
        })
    except PermissionError as e:
        return f"Permission error: {e}"
    except Exception as e:
        return f"Error searching files: {e}"


@mcp.tool()
def file_info(path: str) -> str:
    """Get detailed metadata for a file or directory.

    Args:
        path: Path to inspect.

    Returns:
        Size, permissions, owner, timestamps as a formatted string.
    """
    try:
        p = _safe_path(path)
        if not p.exists():
            return f"Error: path not found — {p}"

        s = p.stat()
        mode = stat.filemode(s.st_mode)
        kind = "directory" if p.is_dir() else "file" if p.is_file() else "other"

        return toon_encode({
            "path": str(p),
            "type": kind,
            "size_bytes": s.st_size,
            "size_kb": round(s.st_size / 1024, 1),
            "mode": mode,
            "modified": datetime.fromtimestamp(s.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "accessed": datetime.fromtimestamp(s.st_atime).strftime("%Y-%m-%d %H:%M:%S"),
            "created": datetime.fromtimestamp(s.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    except PermissionError as e:
        return f"Permission error: {e}"
    except Exception as e:
        return f"Error getting file info: {e}"


@mcp.tool()
def create_directory(path: str) -> str:
    """Create a directory (and any missing parent directories).

    Args:
        path: Directory path to create.

    Returns:
        Success message or error.
    """
    try:
        p = _safe_path(path)
        p.mkdir(parents=True, exist_ok=True)
        return f"Directory created: {p}"
    except PermissionError as e:
        return f"Permission error: {e}"
    except Exception as e:
        return f"Error creating directory: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
