"""Desktop MCP server — GNOME desktop integration tools.

Exposed tools:
  - send_notification   Send a GNOME desktop notification
  - open_url            Open a URL in the default browser
  - open_file           Open a file with its default application
  - get_clipboard       Read clipboard contents
  - set_clipboard       Write to clipboard
  - take_screenshot     Capture the screen to a file
  - get_active_window   Get the currently focused window title/app
"""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("desktop")


def _run(cmd: list[str], timeout: int = 10) -> tuple[bool, str]:
    """Run a subprocess command, return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip() or f"Command failed with code {result.returncode}"
    except FileNotFoundError:
        return False, f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout}s"
    except Exception as e:
        return False, f"Error: {e}"


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def send_notification(
    title: str,
    body: str = "",
    urgency: str = "normal",
    icon: str = "",
) -> str:
    """Send a GNOME desktop notification.

    Args:
        title:   Notification title.
        body:    Optional notification body message.
        urgency: 'low', 'normal', or 'critical' (default: normal).
        icon:    Optional icon name or path (e.g. 'dialog-information').

    Returns:
        Success or error message.
    """
    cmd = ["notify-send", "--urgency", urgency]
    if icon:
        cmd += ["--icon", icon]
    cmd += [title]
    if body:
        cmd.append(body)
    ok, out = _run(cmd)
    return "Notification sent" if ok else f"Failed to send notification: {out}"


@mcp.tool()
def open_url(url: str) -> str:
    """Open a URL in the default browser.

    Args:
        url: The URL to open (must start with http:// or https://).

    Returns:
        Success or error message.
    """
    if not url.startswith(("http://", "https://")):
        return f"Error: only http/https URLs are allowed, got: {url}"
    ok, out = _run(["xdg-open", url])
    return f"Opened: {url}" if ok else f"Failed to open URL: {out}"


@mcp.tool()
def open_file(path: str) -> str:
    """Open a file with its default application via xdg-open.

    Args:
        path: Absolute path to the file to open.

    Returns:
        Success or error message.
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: file not found — {p}"
    ok, out = _run(["xdg-open", str(p)])
    return f"Opened: {p}" if ok else f"Failed to open file: {out}"


@mcp.tool()
def get_clipboard() -> str:
    """Read the current clipboard contents.

    Returns:
        Clipboard text (up to 4096 chars), or an error message.
    """
    # Try wl-paste (Wayland) then xclip (X11) then xsel
    for cmd in [["wl-paste"], ["xclip", "-selection", "clipboard", "-o"], ["xsel", "--clipboard", "--output"]]:
        ok, out = _run(cmd)
        if ok:
            return out[:4096] if out else "(clipboard is empty)"
    return "Error: could not read clipboard — install wl-clipboard, xclip, or xsel"


@mcp.tool()
def set_clipboard(text: str) -> str:
    """Write text to the clipboard.

    Args:
        text: Text to place on the clipboard.

    Returns:
        Success or error message.
    """
    # Try wl-copy (Wayland) then xclip (X11) then xsel
    for cmd_factory in [
        lambda: (["wl-copy"], text),
        lambda: (["xclip", "-selection", "clipboard"], text),
        lambda: (["xsel", "--clipboard", "--input"], text),
    ]:
        cmd, stdin_text = cmd_factory()
        try:
            result = subprocess.run(
                cmd, input=stdin_text, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return f"Clipboard updated ({len(text)} chars)"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "Error: could not write clipboard — install wl-clipboard, xclip, or xsel"


@mcp.tool()
def take_screenshot(output_path: str = "", delay_seconds: int = 0) -> str:
    """Take a screenshot and save it to a file.

    Args:
        output_path:    Where to save the PNG. Defaults to ~/Pictures/Screenshots/.
        delay_seconds:  Seconds to wait before capturing (0 = immediate).

    Returns:
        Path of the saved screenshot, or error message.
    """
    if not output_path:
        screenshots_dir = Path.home() / "Pictures" / "Screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(screenshots_dir / f"screenshot_{ts}.png")

    p = Path(output_path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)

    # Wayland: gnome-screenshot or grim
    # X11: gnome-screenshot or scrot
    for cmd in [
        ["gnome-screenshot", f"--delay={delay_seconds}", f"--file={p}"],
        ["grim", str(p)],
        ["scrot", f"--delay={delay_seconds}", str(p)],
    ]:
        ok, out = _run(cmd, timeout=delay_seconds + 15)
        if ok:
            return f"Screenshot saved: {p}"

    return "Error: could not take screenshot — install gnome-screenshot, grim, or scrot"


@mcp.tool()
def get_active_window() -> str:
    """Get the title and application of the currently focused window.

    Returns:
        Window info as a formatted string, or an error message.
    """
    # xdotool works on X11; for Wayland use hyprctl or swaymsg if available
    ok, out = _run(["xdotool", "getactivewindow", "getwindowname"])
    if ok:
        return f"Active window: {out}"

    # Wayland fallback: try gdbus to ask the Shell
    ok, out = _run([
        "gdbus", "call", "--session",
        "--dest", "org.gnome.Shell",
        "--object-path", "/org/gnome/Shell",
        "--method", "org.gnome.Shell.Eval",
        "global.display.focus_window?.title ?? 'unknown'",
    ])
    if ok:
        return f"Active window (via Shell): {out}"

    return "Error: could not determine active window — install xdotool or run on X11"


if __name__ == "__main__":
    mcp.run(transport="stdio")
