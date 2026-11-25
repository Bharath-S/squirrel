"""The cheatsheet store: one JSON object per line in commands.jsonl.

Plain text on purpose, so it diffs and merges well in git.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import placeholders

# Field order in the file. Unknown fields are kept as they are.
FIELDS = ("id", "cmd", "note", "title", "desc", "tags", "template", "created", "host", "shell", "tidied")


def now_iso() -> str:
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


@dataclass
class Entry:
    cmd: str
    id: str = ""
    note: str = ""
    title: str = ""
    desc: str = ""
    tags: List[str] = field(default_factory=list)
    template: str = ""
    created: str = ""
    host: str = ""
    shell: str = ""
    tidied: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = hashlib.sha1(self.cmd.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def new(cls, cmd: str, note: str = "", shell: str = "") -> Entry:
        return cls(cmd=cmd, id=uuid.uuid4().hex[:12], note=note, created=now_iso(),
                   host=socket.gethostname().split(".")[0], shell=shell)

    @classmethod
    def from_dict(cls, d: Any) -> Optional[Entry]:
        """Build an entry from a parsed JSON line. Returns None if it has no command."""
        if not isinstance(d, dict) or not isinstance(d.get("cmd"), str) or not d["cmd"].strip():
            return None

        def text(key: str) -> str:
            v = d.get(key)
            return v if isinstance(v, str) else ""

        tags = d.get("tags")
        return cls(
            cmd=d["cmd"],
            id=str(d.get("id") or ""),
            note=text("note"),
            title=text("title"),
            desc=text("desc"),
            tags=[str(t) for t in tags] if isinstance(tags, list) else [],
            template=text("template"),
            created=text("created"),
            host=text("host"),
            shell=text("shell"),
            tidied=bool(d.get("tidied")),
            extra={k: v for k, v in d.items() if k not in FIELDS},
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {k: getattr(self, k) for k in FIELDS}
        d.update(self.extra)
        return d

    @property
    def runnable(self) -> str:
        """The template when it has placeholders to fill, otherwise the saved command."""
        return self.template if placeholders.find(self.template) else self.cmd


class Store:
    def __init__(self, path: Path, git_autocommit: bool = False,
                 warn: Callable[[str], None] = lambda msg: None) -> None:
        self.path = Path(path)
        self.git_autocommit = git_autocommit
        self.warn = warn

    @property
    def backup_path(self) -> Path:
        return self.path.with_name(self.path.name + ".bak")

    def ensure(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def load(self) -> List[Entry]:
        if not self.path.exists():
            return []
        entries = []
        with self.path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = Entry.from_dict(json.loads(line))
                except ValueError:
                    entry = None
                if entry is None:
                    self.warn("squirrel: skipping unreadable line %d in %s" % (lineno, self.path))
                    continue
                entries.append(entry)
        return entries

    def append(self, entry: Entry) -> None:
        self.ensure()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(_dump(entry))

    def rewrite(self, entries: List[Entry]) -> None:
        """Replace the whole file atomically. The previous version goes to commands.jsonl.bak."""
        self.ensure()
        shutil.copy2(str(self.path), str(self.backup_path))
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".commands.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(_dump(e))
        os.replace(tmp, str(self.path))

    def commit(self, message: str) -> None:
        """git commit the store, if SQUIRREL_GIT_AUTOCOMMIT is on and the folder is a git repo."""
        repo = str(self.path.parent)
        if not self.git_autocommit or not os.path.isdir(os.path.join(repo, ".git")):
            return
        quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        subprocess.call(["git", "-C", repo, "add", self.path.name], **quiet)
        subprocess.call(["git", "-C", repo, "commit", "-q", "-m", message[:72]], **quiet)


def _dump(entry: Entry) -> str:
    return json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
