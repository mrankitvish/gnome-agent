"""Built-in System MCP server — exposes system introspection tools."""

import os
import shutil
import subprocess

from fastmcp import FastMCP

mcp = FastMCP("system")


@mcp.tool()
def list_processes(sort_by: str = "cpu", limit: int = 15) -> str:
    """List running processes sorted by CPU or memory usage.

    Args:
        sort_by: Sort criteria — 'cpu' or 'memory'.
        limit: Max number of processes to return.
    """
    sort_flag = "-%cpu" if sort_by == "cpu" else "-%mem"
    try:
        result = subprocess.run(
            ["ps", "aux", "--sort", sort_flag],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        # Header + top N processes
        return "\n".join(lines[: limit + 1])
    except Exception as e:
        return f"Error listing processes: {e}"


@mcp.tool()
def disk_usage(path: str = "/") -> str:
    """Get disk usage for a filesystem path.

    Args:
        path: Filesystem path to check (default: root /).
    """
    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        free_gb = usage.free / (1024**3)
        pct = (usage.used / usage.total) * 100
        return (
            f"Disk usage for {path}:\n"
            f"  Total: {total_gb:.1f} GB\n"
            f"  Used:  {used_gb:.1f} GB ({pct:.1f}%)\n"
            f"  Free:  {free_gb:.1f} GB"
        )
    except Exception as e:
        return f"Error getting disk usage: {e}"


@mcp.tool()
def journal_logs(service: str, lines: int = 50) -> str:
    """Get recent systemd journal logs for a service.

    Args:
        service: Systemd service name (e.g. 'sshd', 'NetworkManager').
        lines: Number of recent log lines to return.
    """
    try:
        result = subprocess.run(
            ["journalctl", "-u", service, "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout.strip() or f"No logs found for service: {service}"
    except FileNotFoundError:
        return "journalctl not found — systemd may not be available"
    except Exception as e:
        return f"Error reading journal: {e}"


@mcp.tool()
def system_info() -> str:
    """Get basic system information (hostname, kernel, uptime)."""
    try:
        hostname = subprocess.run(
            ["hostname"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        kernel = subprocess.run(
            ["uname", "-r"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        uptime = subprocess.run(
            ["uptime", "-p"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return f"Hostname: {hostname}\nKernel: {kernel}\nUptime: {uptime}"
    except Exception as e:
        return f"Error getting system info: {e}"


# Entry point for stdio transport
if __name__ == "__main__":
    mcp.run(transport="stdio")
