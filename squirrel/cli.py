"""Command-line interface: argument parsing and dispatch."""
from __future__ import annotations

import argparse
from typing import List, Optional

from . import __version__, commands, ui
from .config import Config


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="squirrel",
                                description="Command cheatsheet engine (used by save / how / squirrel-tidy).")
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = p.add_subparsers(dest="sub", metavar="COMMAND")

    a = sub.add_parser("add", help="add a command")
    a.add_argument("--cmd", required=True)
    a.add_argument("--note", default="")
    a.add_argument("--shell", default="")
    a.set_defaults(func=commands.cmd_add)

    r = sub.add_parser("recent", help="pick recent successful commands from the session log")
    r.add_argument("--log", help="session log written by the shell hook")
    r.add_argument("--history", help="fallback file of recent history lines (no exit codes)")
    r.add_argument("-n", type=int, default=1)
    r.add_argument("--out", required=True)
    r.set_defaults(func=commands.cmd_recent)

    h = sub.add_parser("how", help="search the cheatsheet")
    h.add_argument("words", nargs="*")
    h.add_argument("--ask", help="ask Claude in plain English")
    h.add_argument("--list", action="store_true", help="just print matching commands")
    h.add_argument("--rm", action="store_true", help="delete entries")
    h.add_argument("--edit", action="store_true", help="open the store in $EDITOR")
    h.add_argument("--out", help=argparse.SUPPRESS)
    h.add_argument("--shell", default="")
    h.add_argument("--widget", action="store_true", help=argparse.SUPPRESS)
    h.set_defaults(func=commands.cmd_how)

    s = sub.add_parser("show", help="show one entry (used by the fzf preview)")
    s.add_argument("id")
    s.set_defaults(func=commands.cmd_show)

    t = sub.add_parser("tidy", help="add titles, descriptions, tags and templates with Claude")
    t.add_argument("--all", action="store_true", help="redo entries that were already tidied")
    t.add_argument("--dry-run", action="store_true", help="show exactly what would be sent, send nothing")
    t.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    t.add_argument("--limit", type=int, default=0, help="tidy at most this many entries")
    t.add_argument("--batch", type=int, default=25, help="entries per request (default 25)")
    t.set_defaults(func=commands.cmd_tidy)

    m = sub.add_parser("mask", help="mask secrets in stdin (to check what would be sent)")
    m.set_defaults(func=commands.cmd_mask)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    app = commands.App.from_config(Config.from_env())
    try:
        return args.func(args, app)
    except KeyboardInterrupt:
        ui.say("")
        return 130
