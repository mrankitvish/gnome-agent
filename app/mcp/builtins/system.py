"""Built-in System MCP server — exposes system introspection tools.

All tool outputs are TOON-encoded (via toon_utils) for compact LLM consumption.
If toonify is not installed, outputs fall back to plain text.
"""

import os
import re
import shutil
import subprocess

from fastmcp import FastMCP

mcp = FastMCP("system")

# TOON utils live outside the MCP subprocess — import inline
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).parents[3]))
from app.core.toon_utils import toon_encode, toon_safe


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 10) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip()


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_processes(sort_by: str = "cpu", limit: int = 15) -> str:
    """List running processes sorted by CPU or memory usage.

    Args:
        sort_by: 'cpu' or 'memory'.
        limit:   Max number of processes to return.

    Returns:
        TOON-encoded list of process records.
    """
    sort_flag = "-%cpu" if sort_by == "cpu" else "-%mem"
    try:
        result = subprocess.run(
            ["ps", "aux", "--sort", sort_flag],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        if len(lines) < 2:
            return "No processes found"

        # Parse ps output into structured records
        header = lines[0].split()
        processes = []
        for line in lines[1 : limit + 1]:
            parts = line.split(None, len(header) - 1)
            if len(parts) >= len(header):
                processes.append({
                    "user": parts[0],
                    "pid": int(parts[1]),
                    "cpu": float(parts[2]),
                    "mem": float(parts[3]),
                    "command": parts[-1][:80],  # truncate long commands
                })

        return toon_encode({"processes": processes, "sort_by": sort_by})
    except Exception as e:
        return f"Error listing processes: {e}"


@mcp.tool()
def disk_usage(path: str = "/") -> str:
    """Get disk usage for a filesystem path.

    Args:
        path: Filesystem path to check (default: root /).

    Returns:
        TOON-encoded disk usage record.
    """
    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        pct = (usage.used / usage.total) * 100

        return toon_encode({
            "path": path,
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "used_pct": round(pct, 1),
        })
    except Exception as e:
        return f"Error getting disk usage: {e}"


@mcp.tool()
def journal_logs(service: str, lines: int = 50) -> str:
    """Get recent systemd journal logs for a service.

    Args:
        service: Systemd service name (e.g. 'sshd', 'NetworkManager').
        lines:   Number of recent log lines.

    Returns:
        TOON-encoded log entries.
    """
    try:
        result = subprocess.run(
            ["journalctl", "-u", service, "-n", str(lines), "--no-pager",
             "--output=json-short"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            # Fallback: plain text
            plain = subprocess.run(
                ["journalctl", "-u", service, "-n", str(lines), "--no-pager"],
                capture_output=True, text=True, timeout=15,
            )
            return plain.stdout.strip() or f"No logs for: {service}"

        # Parse JSON lines and TOON-encode
        import json
        entries = []
        for raw in result.stdout.strip().splitlines():
            try:
                obj = json.loads(raw)
                entries.append({
                    "time": obj.get("__REALTIME_TIMESTAMP", ""),
                    "unit": obj.get("_SYSTEMD_UNIT", service),
                    "msg": obj.get("MESSAGE", ""),
                })
            except Exception:
                continue

        if not entries:
            return plain.stdout.strip() if result.stdout else f"No logs for: {service}"

        return toon_encode({"service": service, "logs": entries})
    except FileNotFoundError:
        return "journalctl not found — systemd may not be available"
    except Exception as e:
        return f"Error reading journal: {e}"


@mcp.tool()
def system_info() -> str:
    """Get system information — hostname, kernel, OS, CPU, memory, uptime.

    Returns:
        TOON-encoded system info record.
    """
    try:
        import platform
        hostname = _run(["hostname"])
        kernel = _run(["uname", "-r"])
        uptime = _run(["uptime", "-p"])

        # Memory
        mem_info = {}
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith(("MemTotal", "MemAvailable")):
                        k, v = line.split(":")
                        mem_info[k.strip()] = int(v.strip().split()[0]) // 1024  # MB
        except Exception:
            pass

        return toon_encode({
            "hostname": hostname,
            "kernel": kernel,
            "os": platform.platform(),
            "uptime": uptime,
            "mem_total_mb": mem_info.get("MemTotal"),
            "mem_available_mb": mem_info.get("MemAvailable"),
        })
    except Exception as e:
        return f"Error getting system info: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
