"""Subcommand handlers. Each takes parsed args and an App, and returns an exit code.

The shell wrapper passes `--out FILE` to `how`. The handler writes two lines
there: what to do (insert, run, history or print) and the final command. The
shell then acts on it, because only the shell can edit its own prompt line or
history.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional

from . import clipboard, history, picker, placeholders, prompts, ui
from .claude import ClaudeClient, ClaudeError
from .config import Config
from .masking import mask
from .search import newest_first, search
from .store import Entry, Store

ASK_MAX_ENTRIES = 1500


@dataclass
class App:
    config: Config
    store: Store

    @classmethod
    def from_config(cls, config: Config) -> App:
        return cls(config, Store(config.store_file, config.git_autocommit, warn=ui.say))

    def claude(self) -> ClaudeClient:
        return ClaudeClient(self.config)

    def pick(self, entries: List[Entry], query: str = "", prompt: str = "how> ", multi: bool = False) -> List[Entry]:
        return picker.pick(entries, query, prompt, multi, use_fzf=self.config.use_fzf)


# --------------------------------------------------------------------------- add
def save_command(app: App, cmd: str, note: str = "", shell: str = "") -> int:
    cmd = cmd.replace(history.NL_MARK, "\n").strip()
    if not cmd:
        ui.say("squirrel: nothing to save")
        return 1
    entries = app.store.load()
    for e in entries:
        if e.cmd.strip() != cmd:
            continue
        if note and note != e.note:
            e.note = note
            app.store.rewrite(entries)
            app.store.commit("update note: " + ui.one_line(cmd))
            ui.say(ui.color(ui.GREEN, "Already saved; note updated."))
        else:
            ui.say("Already in your cheatsheet.")
        return 0
    app.store.append(Entry.new(cmd, note=note, shell=shell))
    app.store.commit("save: " + ui.one_line(cmd))
    ui.say(ui.color(ui.GREEN, "Saved") + " to " + str(app.store.path))
    return 0


def cmd_add(args: argparse.Namespace, app: App) -> int:
    return save_command(app, args.cmd, args.note or "", args.shell or "")


# --------------------------------------------------------------------------- recent
def cmd_recent(args: argparse.Namespace, app: App) -> int:
    """Write the chosen recent commands to --out, one per line, for `save` to edit."""
    found = history.recent(args.log, args.history, args.n)
    if found.skipped and args.n == 1:
        status, cmd = found.skipped
        ui.say(ui.color(ui.DIM, "(skipped the last command, it failed with exit %s: %s)" % (status, ui.one_line(cmd))))
    if not found.commands:
        ui.say("No successful commands found in this shell session yet.")
        return 1
    if not found.from_log:
        ui.say(ui.color(ui.DIM, "(exit status unknown: picked from shell history)"))
    if args.n == 1:
        chosen = found.commands[:1]
    else:
        choices = [Entry(cmd=c, id=str(i)) for i, c in enumerate(found.commands)]
        chosen = [e.cmd for e in app.pick(choices, prompt="save> ", multi=True)]
        if not chosen:
            return 1
    with open(args.out, "w", encoding="utf-8") as f:
        for c in chosen:
            f.write(c.replace("\n", history.NL_MARK) + "\n")
    return 0


# --------------------------------------------------------------------------- show
def cmd_show(args: argparse.Namespace, app: App) -> int:
    for e in app.store.load():
        if e.id == args.id:
            print(ui.render_entry(e))
            return 0
    return 1


# --------------------------------------------------------------------------- how
def cmd_how(args: argparse.Namespace, app: App) -> int:
    if args.edit:
        app.store.ensure()
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        return subprocess.call(shlex.split(editor) + [str(app.store.path)])
    entries = app.store.load()
    if args.ask:
        return ask_claude(args, app, entries)
    if not entries:
        ui.say("Your cheatsheet is empty. Run a command, then type `save`.")
        return 1

    words = " ".join(args.words)
    terms = words.lower().split()
    candidates = search(entries, terms) if terms else newest_first(entries)
    if not candidates:
        ui.say("Nothing matches '%s'. Try fewer words, or: how --ask \"%s\"" % (words, words))
        return 1

    if args.list or not ui.interactive() or not (sys.stdout.isatty() or args.widget):
        for e in candidates:
            print(e.cmd)
        return 0
    if args.rm:
        return _delete(app, entries, candidates, words)

    if len(candidates) == 1 and terms:
        chosen = candidates
        if chosen[0].title:
            ui.say(ui.color(ui.CYAN, chosen[0].title))
    else:
        chosen = app.pick(candidates, words if picker.have_fzf(app.config.use_fzf) else "")
    if not chosen:
        return 1
    return deliver(args, app, chosen[0].runnable)


def _delete(app: App, entries: List[Entry], candidates: List[Entry], words: str) -> int:
    chosen = app.pick(candidates, words, prompt="delete> ", multi=True)
    if not chosen:
        return 1
    for e in chosen:
        ui.say("  " + ui.label(e))
    if not ui.confirm("Delete %s?" % ui.count(len(chosen), "entry", "entries")):
        return 1
    ids = {e.id for e in chosen}
    app.store.rewrite([e for e in entries if e.id not in ids])
    app.store.commit("delete %d entries" % len(ids))
    ui.say("Deleted. A backup of the previous file is in %s" % app.store.backup_path.name)
    return 0


def deliver(args: argparse.Namespace, app: App, text: str, offer_save: bool = False) -> int:
    """Fill in placeholders, ask what to do with the command, and hand it to the shell."""
    can_ask = ui.interactive() and (sys.stdout.isatty() or bool(args.widget))
    memory = placeholders.Memory(app.config.state_file)
    final = placeholders.fill(text, _ask_placeholder, memory) if can_ask else text

    action = "print"
    if args.widget:
        action = "insert"
    elif can_ask and args.out:
        action = _choose_action(args, app, text, final, offer_save)
        if action is None:
            return 1

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(action + "\n" + final + "\n")
    if not args.out or action == "print":
        print(final)
    return 0


def _ask_placeholder(name: str, default: str) -> str:
    return ui.ask("  " + ui.color(ui.YELLOW, "<" + name + ">"), default)


def _choose_action(args: argparse.Namespace, app: App, text: str, final: str, offer_save: bool) -> Optional[str]:
    ui.say(ui.color(ui.GREEN, "→ ") + ui.color(ui.BOLD, final))
    on_enter = "put on prompt" if args.shell == "zsh" else "add to history (↑ to edit)"
    save_hint = "   s save" if offer_save else ""
    answer = ui.ask("[Enter] %s   r run   c copy   p print%s   q quit" % (on_enter, save_hint), "").strip().lower()
    if answer.startswith("q"):
        return None
    if answer.startswith("r"):
        return "run"
    if answer.startswith("c"):
        where = clipboard.copy(final)
        ui.say(("Copied via " + where) if where else "No clipboard tool found.")
        return "history"
    if answer.startswith("p"):
        return "print"
    if answer.startswith("s") and offer_save:
        save_command(app, text, ui.ask("Note (optional)", ""), args.shell)
    return "insert"


# --------------------------------------------------------------------------- how --ask
def ask_claude(args: argparse.Namespace, app: App, entries: List[Entry]) -> int:
    items = [{"id": e.id, "title": e.title, "cmd": mask(e.template or e.cmd)[0],
              "tags": e.tags, "desc": mask(e.desc or e.note)[0]}
             for e in entries[-ASK_MAX_ENTRIES:]]
    user = json.dumps({"question": mask(args.ask)[0], "os": platform.system(),
                       "shell": args.shell or os.path.basename(os.environ.get("SHELL", "")),
                       "cheatsheet": items}, ensure_ascii=False)
    client = app.claude()
    ui.say(ui.color(ui.DIM, "Asking Claude (%s)..." % client.model))
    try:
        result = client.request_json(prompts.ASK_SYSTEM, user, prompts.ASK_SCHEMA, max_tokens=4000)
    except ClaudeError as err:
        ui.say("squirrel: %s" % err)
        return 1

    if result.get("explanation"):
        ui.say(ui.color(ui.DIM, result["explanation"]))
    by_id = {e.id: e for e in entries}
    found = [by_id[i] for i in result.get("matches", []) if i in by_id]
    if found:
        chosen = found if len(found) == 1 else app.pick(found)
        if not chosen:
            return 1
        return deliver(args, app, chosen[0].runnable)

    suggestion = (result.get("suggestion") or "").strip()
    if not suggestion:
        ui.say("Claude found nothing for that.")
        return 1
    ui.say(ui.color(ui.YELLOW, "Not from your cheatsheet (suggested by Claude, check it before running):"))
    return deliver(args, app, suggestion, offer_save=True)


# --------------------------------------------------------------------------- tidy
def cmd_tidy(args: argparse.Namespace, app: App) -> int:
    entries = app.store.load()
    todo = [e for e in entries if args.all or not e.tidied]
    if args.limit:
        todo = todo[:args.limit]
    if not todo:
        ui.say("Nothing to tidy: every entry already has a title. Use --all to redo them.")
        return 0

    payload, masked = [], 0
    for e in todo:
        cmd, n1 = mask(e.cmd)
        note, n2 = mask(e.note)
        masked += n1 + n2
        payload.append({"id": e.id, "cmd": cmd, "note": note})
    what = "%s (%s masked)" % (ui.count(len(payload), "entry", "entries"), ui.count(masked, "secret", "secrets"))

    client = app.claude()
    if args.dry_run:
        ui.say("Would send %s to %s:" % (what, client.model))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if not app.config.api_key:
        ui.say("squirrel-tidy: set ANTHROPIC_API_KEY first (see README).")
        return 1
    ui.say("%s to tidy. Preview with: squirrel-tidy --dry-run" % what)
    if not args.yes and not ui.confirm("Send them to Claude (%s)?" % client.model):
        return 1

    by_id = {e.id: e for e in entries}
    done = 0
    for start in range(0, len(payload), args.batch):
        batch = payload[start:start + args.batch]
        ui.say(ui.color(ui.DIM, "  batch %d-%d..." % (start + 1, start + len(batch))))
        try:
            result = client.request_json(prompts.TIDY_SYSTEM, json.dumps({"entries": batch}, ensure_ascii=False),
                                         prompts.TIDY_SCHEMA)
        except ClaudeError as err:
            ui.say("squirrel-tidy: %s" % err)
            break
        for r in result.get("entries", []):
            e = by_id.get(r.get("id"))
            if e is not None:
                apply_tidy(e, r)
                done += 1
        app.store.rewrite(entries)  # keep progress after every batch
    if done:
        app.store.commit("squirrel-tidy: %d entries" % done)
    ui.say(ui.color(ui.GREEN, "Tidied %s." % ui.count(done, "entry", "entries")))
    return 0 if done else 1


def apply_tidy(e: Entry, r: dict) -> None:
    """Copy Claude's title, description, tags and template onto an entry. The command never changes."""
    e.title = r.get("title", "").strip()
    e.desc = r.get("description", "").strip()
    e.tags = [t.strip().lower() for t in r.get("tags", []) if t.strip()][:6]
    template = r.get("template", "").strip()
    e.template = template if template and template != e.cmd else ""
    e.tidied = True


# --------------------------------------------------------------------------- mask
def cmd_mask(args: argparse.Namespace, app: App) -> int:
    out, n = mask(sys.stdin.read())
    sys.stdout.write(out)
    ui.say("(%d masked)" % n)
    return 0
