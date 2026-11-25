"""Copy text to the clipboard on macOS, Linux (X11 or Wayland), WSL, or over SSH (OSC 52)."""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
from typing import List, Optional

TOOLS: List[List[str]] = [
    ["pbcopy"],
    ["wl-copy"],
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
    ["clip.exe"],
]


def _usable(tool: str) -> bool:
    if not shutil.which(tool):
        return False
    if tool == "wl-copy":
        return bool(os.environ.get("WAYLAND_DISPLAY"))
    if tool.startswith("x"):
        return bool(os.environ.get("DISPLAY"))
    return True


def copy(text: str) -> Optional[str]:
    """Copy text. Returns how it was copied, or None if nothing worked."""
    for tool in TOOLS:
        if not _usable(tool[0]):
            continue
        try:
            subprocess.run(tool, input=text.encode("utf-8"), check=True, timeout=5)
            return tool[0]
        except (subprocess.SubprocessError, OSError):
            continue
    # OSC 52 works in most modern terminals (iTerm2, kitty, WezTerm, Windows Terminal,
    # and tmux with set-clipboard on), including over SSH.
    try:
        with open("/dev/tty", "w") as tty:
            tty.write("\033]52;c;" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "\a")
        return "terminal (OSC 52)"
    except OSError:
        return None
