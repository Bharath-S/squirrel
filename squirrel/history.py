"""Find the recent commands that `save` can offer.

The shell hook writes one "exit-status<TAB>command" line per command to a
per-session log; newlines inside a command are written as NL_MARK. When the
log is empty (a brand-new shell), plain shell history is used and exit codes
are unknown ("?").
"""
from __future__ import annotations

import os
from typing import List, NamedTuple, Optional, Sequence, Tuple

NL_MARK = "\x1f"
UNKNOWN = "?"
SELF_COMMANDS = ("save", "how", "squirrel-tidy")

Record = Tuple[str, str]  # (exit status, command)


class Recent(NamedTuple):
    commands: List[str]          # newest first, no duplicates
    skipped: Optional[Record]    # the newest command, if it failed and was skipped
    from_log: bool               # False when exit codes were unknown


def is_self(cmd: str) -> bool:
    words = cmd.split(None, 1)
    return bool(words) and words[0] in SELF_COMMANDS


def read_log(path: Optional[str]) -> List[Record]:
    records = []
    if path and os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if "\t" not in line:
                    continue
                status, cmd = line.split("\t", 1)
                cmd = cmd.replace(NL_MARK, "\n")
                if cmd.strip() and not is_self(cmd):
                    records.append((status, cmd))
    return records


def read_history(path: Optional[str]) -> List[Record]:
    records = []
    if path and os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                cmd = line.strip()
                if cmd and not is_self(cmd):
                    records.append((UNKNOWN, cmd))
    return records


def select(records: Sequence[Record], n: int) -> Tuple[List[str], Optional[Record]]:
    """Newest n successful commands (oldest-first input), and the failed one skipped at the top."""
    ok: List[str] = []
    skipped: Optional[Record] = None
    seen = set()
    for status, cmd in reversed(records):
        if status not in ("0", UNKNOWN):
            if not ok and skipped is None:
                skipped = (status, cmd)
            continue
        if cmd in seen:
            continue
        seen.add(cmd)
        ok.append(cmd)
        if len(ok) >= n:
            break
    return ok, skipped


def recent(log_path: Optional[str], history_path: Optional[str], n: int) -> Recent:
    records = read_log(log_path)
    from_log = bool(records)
    if not from_log:
        records = read_history(history_path)
    commands, skipped = select(records, n)
    return Recent(commands, skipped, from_log)
