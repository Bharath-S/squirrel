"""<placeholders> in saved commands: `<name>` or `<name:default>`.

The last value typed for each name is remembered in a small state file, except
for names that look like secrets.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

PATTERN = re.compile(r"<([A-Za-z_][A-Za-z0-9_.-]*)(?::([^<>\n]*))?>")
SECRET_NAME = re.compile(r"(?i)secret|token|passw|pwd|api_?key|private")


def find(text: str) -> List[Tuple[str, Optional[str]]]:
    """Unique (name, default) pairs in order of first appearance."""
    found: List[Tuple[str, Optional[str]]] = []
    seen = set()
    for m in PATTERN.finditer(text or ""):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            found.append((m.group(1), m.group(2)))
    return found


def substitute(text: str, values: Dict[str, str]) -> str:
    """Replace placeholders that have a value; leave the rest as they are."""
    return PATTERN.sub(lambda m: values.get(m.group(1)) or m.group(0), text)


class Memory:
    """Remembers the last value used for each placeholder name."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> Dict[str, str]:
        try:
            with self.path.open(encoding="utf-8") as f:
                data = json.load(f)
            last = data.get("last", {})
            return last if isinstance(last, dict) else {}
        except (OSError, ValueError, AttributeError):
            return {}

    def save(self, last: Dict[str, str]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", encoding="utf-8") as f:
                json.dump({"last": last}, f)
        except OSError:
            pass


def fill(text: str, ask: Callable[[str, str], str], memory: Memory) -> str:
    """Ask for each placeholder's value and return the filled-in command."""
    found = find(text)
    if not found:
        return text
    last = memory.load()
    values = {}
    for name, default in found:
        value = ask(name, last.get(name) or default or "")
        values[name] = value
        if value and not SECRET_NAME.search(name):
            last[name] = value
    memory.save(last)
    return substitute(text, values)
