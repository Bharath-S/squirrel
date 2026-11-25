"""Let the user pick entries: fzf when it is installed, a numbered list otherwise."""
from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence

from . import ui
from .store import Entry

# The folder that contains the `squirrel` package. fzf runs the preview command from
# here, so `python -m squirrel` finds this copy of the package.
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
NUMBERED_LIMIT = 30


def have_fzf(enabled: bool = True) -> bool:
    return enabled and shutil.which("fzf") is not None


def pick(entries: Sequence[Entry], query: str = "", prompt: str = "how> ",
         multi: bool = False, use_fzf: bool = True) -> List[Entry]:
    """Return the chosen entries; an empty list means the user cancelled."""
    if not entries:
        return []
    if have_fzf(use_fzf):
        return _pick_fzf(entries, query, prompt, multi)
    return _pick_numbered(entries, multi)


def _pick_fzf(entries: Sequence[Entry], query: str, prompt: str, multi: bool) -> List[Entry]:
    preview = shlex.quote(sys.executable) + " -m squirrel show {1}"
    lines = "".join(e.id + "\t" + ui.fzf_label(e) + "\n" for e in entries)
    cmd = ["fzf", "--ansi", "--delimiter=\t", "--with-nth=2..", "--height=60%", "--reverse",
           "--prompt=" + prompt, "--query=" + query, "--preview=" + preview,
           "--preview-window=down,40%,wrap", "--bind=ctrl-/:toggle-preview",
           "--header=Enter: choose   Ctrl-/: toggle preview   Esc: cancel"]
    if multi:
        cmd += ["--multi", "--header=Tab: mark several   Enter: choose   Esc: cancel"]
    result = subprocess.run(cmd, input=lines.encode("utf-8"), stdout=subprocess.PIPE, cwd=str(PACKAGE_ROOT))
    if result.returncode != 0:
        return []
    by_id = {e.id: e for e in entries}
    ids = [line.split("\t", 1)[0] for line in result.stdout.decode("utf-8").splitlines() if line]
    return [by_id[i] for i in ids if i in by_id]


def _pick_numbered(entries: Sequence[Entry], multi: bool) -> List[Entry]:
    shown = entries[:NUMBERED_LIMIT]
    for i, e in enumerate(shown, 1):
        ui.say("%3d) %s" % (i, ui.label(e)))
    if len(entries) > len(shown):
        ui.say("     ... %d more; narrow it down with search words" % (len(entries) - len(shown)))
    answer = ui.ask("Pick %s" % ("numbers (e.g. 1 3)" if multi else "a number"), "1")
    chosen = []
    for token in answer.replace(",", " ").split():
        if token.isdigit() and 1 <= int(token) <= len(shown):
            chosen.append(shown[int(token) - 1])
        if chosen and not multi:
            break
    return chosen
