"""Terminal helpers: messages, prompts, colors and how entries are displayed.

Messages and prompts go to stderr so stdout stays clean for piping.
"""
from __future__ import annotations

import os
import sys
from typing import IO, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .store import Entry

DIM, BOLD, CYAN, YELLOW, GREEN, RESET = "\033[2m", "\033[1m", "\033[36m", "\033[33m", "\033[32m", "\033[0m"

_tty: Optional[IO[str]] = None


def tty_in() -> IO[str]:
    """Read answers from the terminal even when stdin is redirected."""
    global _tty
    if _tty is None:
        try:
            _tty = open("/dev/tty")
        except OSError:
            _tty = sys.stdin
    return _tty


def say(*parts: object) -> None:
    print(*parts, file=sys.stderr)


def color(code: str, text: str) -> str:
    if not sys.stderr.isatty() or os.environ.get("NO_COLOR"):
        return text
    return code + text + RESET


def ask(prompt: str, default: str = "") -> str:
    """Ask a question on the terminal. Ctrl-D raises KeyboardInterrupt."""
    shown = "%s [%s]: " % (prompt, default) if default else "%s: " % prompt
    sys.stderr.write(shown)
    sys.stderr.flush()
    line = tty_in().readline()
    if not line:
        raise KeyboardInterrupt
    line = line.rstrip("\n")
    return line if line else default


def confirm(prompt: str) -> bool:
    return ask(prompt + " [y/N]", "n").strip().lower() == "y"


def interactive() -> bool:
    try:
        with open("/dev/tty"):
            return sys.stderr.isatty()
    except OSError:
        return False


def one_line(s: str) -> str:
    return s.replace("\n", " ⏎ ")


def count(n: int, singular: str, plural: str) -> str:
    return "%d %s" % (n, singular if n == 1 else plural)


# --------------------------------------------------------------------------- entry display
def label(e: Entry) -> str:
    """Plain one-line label, used by the numbered picker."""
    parts = []
    if e.title:
        parts.append(e.title + ":")
    parts.append(one_line(e.cmd))
    if e.tags:
        parts.append(" ".join("#" + t for t in e.tags))
    extra = e.desc or e.note
    if extra:
        parts.append("- " + one_line(extra))
    return "  ".join(parts)


def fzf_label(e: Entry) -> str:
    """Colored one-line label for fzf (--ansi). Tabs are fzf's field separator, so they go."""
    title = (CYAN + BOLD + e.title + RESET + "  ") if e.title else ""
    tags = ("  " + YELLOW + " ".join("#" + t for t in e.tags) + RESET) if e.tags else ""
    extra = e.desc or e.note
    extra = ("  " + DIM + "- " + one_line(extra) + RESET) if extra else ""
    return (title + one_line(e.cmd) + tags + extra).replace("\t", " ")


def render_entry(e: Entry) -> str:
    """Multi-line view of one entry, used by the fzf preview pane."""
    lines = []
    if e.title:
        lines.append(BOLD + e.title + RESET)
    lines.append(e.cmd)
    if e.template and e.template != e.cmd:
        lines.append(DIM + "template: " + RESET + e.template)
    if e.desc:
        lines.append(e.desc)
    if e.note:
        lines.append(DIM + "note: " + RESET + e.note)
    if e.tags:
        lines.append(YELLOW + " ".join("#" + t for t in e.tags) + RESET)
    meta = " ".join(x for x in (e.created[:10], e.host) if x)
    if meta:
        lines.append(DIM + "saved " + meta + RESET)
    return "\n".join(lines)
