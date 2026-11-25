#!/usr/bin/env python3
"""cheats.py - the engine behind `save`, `how` and `cheat-tidy`.

Standard library only (Python 3.8+). The shell functions in cheats.sh call
this script; you can also run it directly:  python3 cheats.py --help

Store: one JSON object per line in $CHEATS_DIR/commands.jsonl (default ~/cheats).
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid

STORE_DIR = os.path.expanduser(os.environ.get("CHEATS_DIR", "~/cheats"))
STORE = os.path.join(STORE_DIR, "commands.jsonl")
CACHE_DIR = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "cheats")
STATE = os.path.join(CACHE_DIR, "state.json")

API_URL = os.environ.get("CHEATS_API_URL", "https://api.anthropic.com/v1/messages")
MODEL = os.environ.get("CHEATS_MODEL", "claude-opus-5-5")
# Models that accept the server-side refusal fallback ("fallbacks": "default").
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
                   "claude-fable-5-2", "claude-fable-5-1"}

SELF_CMDS = ("save", "how", "cheat-tidy")
PLACEHOLDER = re.compile(r"<([A-Za-z_][A-Za-z0-9_.-]*)(?::([^<>\n]*))?>")
NL_MARK = "\x1f"  # newline marker used in the shell<->python line protocol
SECRETISH = re.compile(r"(?i)secret|token|passw|pwd|api_?key|private")  # placeholder values never remembered

C_DIM, C_BOLD, C_CYAN, C_YEL, C_GRN, C_OFF = "\033[2m", "\033[1m", "\033[36m", "\033[33m", "\033[32m", "\033[0m"


# --------------------------------------------------------------------------- terminal i/o
_tty = None


def tty_in():
    global _tty
    if _tty is None:
        try:
            _tty = open("/dev/tty")
        except OSError:
            _tty = sys.stdin
    return _tty


def say(*parts):
    print(*parts, file=sys.stderr)


def color(code, text):
    if not sys.stderr.isatty() or os.environ.get("NO_COLOR"):
        return text
    return code + text + C_OFF


def ask(prompt, default=""):
    shown = "%s [%s]: " % (prompt, default) if default else "%s: " % prompt
    sys.stderr.write(shown)
    sys.stderr.flush()
    line = tty_in().readline()
    if not line:  # Ctrl-D
        raise KeyboardInterrupt
    line = line.rstrip("\n")
    return line if line else default


def interactive():
    try:
        with open("/dev/tty"):
            return sys.stderr.isatty()
    except OSError:
        return False


def one_line(s):
    return s.replace("\n", " ⏎ ")


# --------------------------------------------------------------------------- store
def now_iso():
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def normalize(e):
    e.setdefault("id", hashlib.sha1(e["cmd"].encode("utf-8")).hexdigest()[:12])
    for k in ("note", "title", "desc", "template", "created"):
        if not isinstance(e.get(k), str):
            e[k] = ""
    if not isinstance(e.get("tags"), list):
        e["tags"] = []
    return e


def load():
    entries = []
    if not os.path.exists(STORE):
        return entries
    with open(STORE, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                say("cheats: skipping unreadable line %d in %s" % (i, STORE))
                continue
            if isinstance(e, dict) and isinstance(e.get("cmd"), str) and e["cmd"].strip():
                entries.append(normalize(e))
    return entries


def ensure_store():
    os.makedirs(STORE_DIR, exist_ok=True)
    if not os.path.exists(STORE):
        open(STORE, "a").close()


def append(e):
    ensure_store()
    with open(STORE, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")


def rewrite(entries):
    ensure_store()
    shutil.copy2(STORE, STORE + ".bak")
    fd, tmp = tempfile.mkstemp(dir=STORE_DIR, prefix=".commands.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    os.replace(tmp, STORE)


def autocommit(msg):
    if os.environ.get("CHEATS_GIT_AUTOCOMMIT") != "1" or not os.path.isdir(os.path.join(STORE_DIR, ".git")):
        return
    subprocess.call(["git", "-C", STORE_DIR, "add", "commands.jsonl"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.call(["git", "-C", STORE_DIR, "commit", "-q", "-m", msg[:72]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except OSError:
        pass


# --------------------------------------------------------------------------- secret masking
MASK = "<secret>"
_SECRET_RULES = [
    # whole private key blocks
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), MASK),
    # well-known token formats
    (re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}"), MASK),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"), MASK),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), MASK),
    (re.compile(r"\bglpat-[A-Za-z0-9_-]{16,}"), MASK),
    (re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), MASK),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"), MASK),
    (re.compile(r"\bnpm_[A-Za-z0-9]{30,}"), MASK),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), MASK),
    # user:password@ in URLs
    (re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^/\s:@]+:)[^@\s/]+@"), r"\1" + MASK + "@"),
    # auth headers
    (re.compile(r"(?i)((?:proxy-)?authorization\s*:\s*(?:bearer|basic|token|digest)?\s*)[^\s'\"]+"), r"\1" + MASK),
    (re.compile(r"(?i)((?:x-api-key|api-key|x-auth-token|private-token|x-access-token)\s*:\s*)[^\s'\"]+"), r"\1" + MASK),
    # --password VALUE / -token VALUE style flags
    (re.compile(r"(?i)((?:^|\s)--?(?:password|passwd|pass|token|api-?key|secret|access-key|secret-key|auth-token|"
                r"client-secret|key-password|storepass|keypass)\s+)(['\"]?)[^\s'\"]+\2"), r"\1\2" + MASK + r"\2"),
    # NAME=value where NAME looks secret (also --password=value, export GITHUB_TOKEN=...)
    (re.compile(r"(?i)\b([A-Za-z0-9_.-]*(?:password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|"
                r"private[_-]?key|credential|storepass|keypass)[A-Za-z0-9_]*\s*=\s*)(['\"]?)[^\s'\"&]+\2"),
     r"\1\2" + MASK + r"\2"),
    # "password": "value" in inline JSON
    (re.compile(r"(?i)(\"[\w.-]*(?:password|secret|token|api[_-]?key|apikey)[\w.-]*\"\s*:\s*\")[^\"]*(\")"),
     r"\1" + MASK + r"\2"),
    # mysql -pPASSWORD, sshpass -p PASSWORD, curl -u user:password
    (re.compile(r"(\b(?:mysql|mysqldump|mysqladmin|mariadb)\b[^\n|;&]*?\s-p)(?=[^\s-])\S+"), r"\1" + MASK),
    (re.compile(r"(\bsshpass\s+-p\s*)\S+"), r"\1" + MASK),
    (re.compile(r"((?:^|\s)(?:-u|--user)\s+['\"]?[^:\s'\"]+:)[^\s'\"]+"), r"\1" + MASK),
]
_LONG_TOKEN = re.compile(r"[A-Za-z0-9+/_=-]{32,}")


def _looks_random(tok):
    return (any(c.isdigit() for c in tok) and any(c.islower() for c in tok)
            and any(c.isupper() for c in tok))


def mask(text):
    """Return (masked_text, number_of_replacements)."""
    n = 0
    for rx, repl in _SECRET_RULES:
        text, k = rx.subn(repl, text)
        n += k
    n += sum(1 for m in _LONG_TOKEN.finditer(text) if _looks_random(m.group(0)))
    text = _LONG_TOKEN.sub(lambda m: MASK if _looks_random(m.group(0)) else m.group(0), text)
    return text, n


# --------------------------------------------------------------------------- search
FIELD_WEIGHTS = (("title", 3.0), ("tags", 2.5), ("cmd", 2.0), ("template", 2.0), ("desc", 1.0), ("note", 1.0))
_WORD = re.compile(r"[A-Za-z0-9_.-]+")


def _subseq(term, word):
    it = iter(word)
    return all(c in it for c in term)


def _term_score(term, text):
    i = text.find(term)
    if i >= 0:
        return 1.0 if i == 0 or not text[i - 1].isalnum() else 0.6
    if len(term) >= 3 and any(_subseq(term, w) for w in _WORD.findall(text)):
        return 0.25
    return 0.0


def entry_text(e, field):
    v = e.get(field, "")
    return (" ".join(v) if isinstance(v, list) else v).lower()


def search(entries, terms):
    scored = []
    for e in entries:
        texts = [(entry_text(e, f), w) for f, w in FIELD_WEIGHTS]
        total = 0.0
        for t in terms:
            best = max(_term_score(t, txt) * w for txt, w in texts)
            if best == 0:
                break
            total += best
        else:
            scored.append((total, e.get("created", ""), e))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [e for _, _, e in scored]


def label(e):
    parts = []
    if e["title"]:
        parts.append(e["title"] + ":")
    parts.append(one_line(e["cmd"]))
    if e["tags"]:
        parts.append(" ".join("#" + t for t in e["tags"]))
    extra = e["desc"] or e["note"]
    if extra:
        parts.append("- " + one_line(extra))
    return "  ".join(parts)


def fzf_label(e):
    # colors are passed to fzf with --ansi; tabs are field separators so strip them
    title = (C_CYAN + C_BOLD + e["title"] + C_OFF + "  ") if e["title"] else ""
    tags = ("  " + C_YEL + " ".join("#" + t for t in e["tags"]) + C_OFF) if e["tags"] else ""
    extra = e["desc"] or e["note"]
    extra = ("  " + C_DIM + "- " + one_line(extra) + C_OFF) if extra else ""
    return (title + one_line(e["cmd"]) + tags + extra).replace("\t", " ")


def have_fzf():
    return os.environ.get("CHEATS_NO_FZF") != "1" and shutil.which("fzf") is not None


def pick(entries, query="", prompt="how> ", multi=False):
    """Let the user pick entries. Returns a list (empty if cancelled)."""
    if not entries:
        return []
    if have_fzf():
        me = shlex.quote(sys.executable) + " " + shlex.quote(os.path.abspath(__file__))
        lines = "\n".join(e["id"] + "\t" + fzf_label(e) for e in entries) + "\n"
        cmd = ["fzf", "--ansi", "--delimiter=\t", "--with-nth=2..", "--height=60%", "--reverse",
               "--prompt=" + prompt, "--query=" + query, "--preview=" + me + " show {1}",
               "--preview-window=down,40%,wrap", "--bind=ctrl-/:toggle-preview",
               "--header=Enter: choose   Ctrl-/: toggle preview   Esc: cancel"]
        if multi:
            cmd += ["--multi", "--header=Tab: mark several   Enter: choose   Esc: cancel"]
        p = subprocess.run(cmd, input=lines.encode("utf-8"), stdout=subprocess.PIPE)
        if p.returncode != 0:
            return []
        ids = [ln.split("\t", 1)[0] for ln in p.stdout.decode("utf-8").splitlines() if ln]
        by_id = {e["id"]: e for e in entries}
        return [by_id[i] for i in ids if i in by_id]
    # numbered fallback
    shown = entries[:30]
    for i, e in enumerate(shown, 1):
        say("%3d) %s" % (i, label(e)))
    if len(entries) > len(shown):
        say("     ... %d more; narrow it down with search words" % (len(entries) - len(shown)))
    ans = ask("Pick %s" % ("numbers (e.g. 1 3)" if multi else "a number"), "1")
    out = []
    for tok in ans.replace(",", " ").split():
        if tok.isdigit() and 1 <= int(tok) <= len(shown):
            out.append(shown[int(tok) - 1])
        if out and not multi:
            break
    return out


# --------------------------------------------------------------------------- placeholders
def fill_placeholders(text):
    found = []
    for m in PLACEHOLDER.finditer(text):
        name, default = m.group(1), m.group(2)
        if name not in [n for n, _ in found]:
            found.append((name, default))
    if not found:
        return text
    state = load_state()
    last = state.setdefault("last", {})
    values = {}
    for name, default in found:
        dflt = last.get(name) or default or ""
        val = ask("  " + color(C_YEL, "<" + name + ">"), dflt)
        values[name] = val
        if val and not SECRETISH.search(name):  # never remember tokens/passwords
            last[name] = val
    save_state(state)

    def sub(m):
        v = values.get(m.group(1), "")
        return v if v else m.group(0)
    return PLACEHOLDER.sub(sub, text)


# --------------------------------------------------------------------------- clipboard
def copy_to_clipboard(text):
    for tool in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["clip.exe"]):
        if shutil.which(tool[0]) and (tool[0] != "wl-copy" or os.environ.get("WAYLAND_DISPLAY")) \
                and (not tool[0].startswith("x") or os.environ.get("DISPLAY")):
            try:
                subprocess.run(tool, input=text.encode("utf-8"), check=True, timeout=5)
                return tool[0]
            except (subprocess.SubprocessError, OSError):
                continue
    # OSC 52: most modern terminals (iTerm2, kitty, WezTerm, Windows Terminal, tmux with set-clipboard on)
    import base64
    try:
        with open("/dev/tty", "w") as t:
            t.write("\033]52;c;" + base64.b64encode(text.encode("utf-8")).decode("ascii") + "\a")
        return "terminal (OSC 52)"
    except OSError:
        return None


# --------------------------------------------------------------------------- Claude API
def call_claude(system, user, schema, max_tokens=16000):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set (export it in your shell, e.g. in ~/.zshrc).")
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"format": {"type": "json_schema", "schema": schema}},
    }
    headers = {"content-type": "application/json", "x-api-key": key, "anthropic-version": "2026-10-21"}
    if MODEL in FALLBACK_MODELS and os.environ.get("CHEATS_NO_FALLBACK") != "1":
        body["fallbacks"] = "default"
        headers["anthropic-beta"] = "server-side-fallback-2026-07-01"
    if os.environ.get("CHEATS_EFFORT"):
        body["output_config"]["effort"] = os.environ["CHEATS_EFFORT"]
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        raise RuntimeError("Claude API error %s: %s" % (e.code, detail))
    except urllib.error.URLError as e:
        raise RuntimeError("Could not reach the Claude API: %s" % e.reason)
    stop = resp.get("stop_reason")
    if stop == "refusal":
        raise RuntimeError("Claude declined this request.")
    if stop == "max_tokens":
        raise RuntimeError("Claude's answer was cut off (max_tokens); try fewer entries with --batch.")
    text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    try:
        return json.loads(text)
    except ValueError:
        raise RuntimeError("Claude returned something that isn't JSON:\n" + text[:500])


TIDY_SYSTEM = """You tidy a personal command-line cheatsheet. For each entry you get the raw command the user ran \
and their optional note. Return, for every entry id:
- title: 2-6 words saying what the command does, e.g. "Install APK on device".
- description: one sentence explaining what it does and any important flag.
- tags: 1-4 short lowercase tags (tool name first, e.g. "adb", "android").
- template: the same command with values that change between uses replaced by <placeholders> with short snake_case \
names, e.g. "adb -s <device> install -r <apk_path>". Keep flags, options and fixed parts exactly as given. You may add \
a default as <name:default> when the original value is a sensible default (ports, common branch names). Values that \
were masked as <secret> stay as a placeholder, named for what they are (e.g. <api_token>). If nothing varies, return \
the command unchanged. Never invent new flags."""

ASK_SYSTEM = """You help someone find a shell command in their personal cheatsheet. You get their question, \
their OS and shell, and the cheatsheet entries (id, title, command, tags, description). Secrets were replaced with \
<secret>. Return:
- matches: ids of the entries that answer the question, best first, at most 5. Empty if none really fits.
- suggestion: only when no entry fits, one command that does what they asked on their OS and shell, using \
<placeholders> for values they must fill in. Otherwise an empty string.
- explanation: one short sentence about the suggestion or the best match."""


# --------------------------------------------------------------------------- subcommands
def cmd_add(args):
    cmd = args.cmd.replace(NL_MARK, "\n").strip()
    if not cmd:
        say("cheats: nothing to save")
        return 1
    entries = load()
    for e in entries:
        if e["cmd"].strip() == cmd:
            if args.note and args.note != e["note"]:
                e["note"] = args.note
                rewrite(entries)
                autocommit("update note: " + one_line(cmd))
                say(color(C_GRN, "Already saved; note updated."))
            else:
                say("Already in your cheatsheet.")
            return 0
    e = {"id": uuid.uuid4().hex[:12], "cmd": cmd, "note": args.note or "", "title": "", "desc": "",
         "tags": [], "template": "", "created": now_iso(), "host": socket.gethostname().split(".")[0],
         "shell": args.shell or "", "tidied": False}
    append(e)
    autocommit("save: " + one_line(cmd))
    say(color(C_GRN, "Saved") + " to " + STORE)
    return 0


def _is_self(cmd):
    first = cmd.strip().split(None, 1)[0] if cmd.strip() else ""
    return first in SELF_CMDS


def cmd_recent(args):
    """Pick recent successful commands from the session log; write them to --out, one per line."""
    records = []
    if args.log and os.path.exists(args.log):
        with open(args.log, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if "\t" not in line:
                    continue
                status, cmd = line.split("\t", 1)
                cmd = cmd.replace(NL_MARK, "\n")
                if cmd.strip() and not _is_self(cmd):
                    records.append((status, cmd))
    from_log = bool(records)
    if not records and args.history and os.path.exists(args.history):
        with open(args.history, encoding="utf-8", errors="replace") as f:
            for line in f:
                cmd = line.strip()
                if cmd and not _is_self(cmd):
                    records.append(("?", cmd))
    records.reverse()  # newest first
    seen, ok, skipped = set(), [], []
    for status, cmd in records:
        if status not in ("0", "?"):
            if not ok and not skipped:
                skipped.append((status, cmd))
            continue
        if cmd in seen:
            continue
        seen.add(cmd)
        ok.append(cmd)
        if len(ok) >= args.n:
            break
    if skipped and args.n == 1:
        say(color(C_DIM, "(skipped the last command, it failed with exit %s: %s)" % (skipped[0][0], one_line(skipped[0][1]))))
    if not ok:
        say("No successful commands found in this shell session yet.")
        return 1
    if not from_log:
        say(color(C_DIM, "(exit status unknown: picked from shell history)"))
    if args.n == 1:
        chosen = ok[:1]
    else:
        fake = [normalize({"id": str(i), "cmd": c}) for i, c in enumerate(ok)]
        chosen = [e["cmd"] for e in pick(fake, prompt="save> ", multi=True)]
        if not chosen:
            return 1
    with open(args.out, "w", encoding="utf-8") as f:
        for c in chosen:
            f.write(c.replace("\n", NL_MARK) + "\n")
    return 0


def cmd_show(args):
    for e in load():
        if e["id"] == args.id:
            if e["title"]:
                print(C_BOLD + e["title"] + C_OFF)
            print(e["cmd"])
            if e["template"] and e["template"] != e["cmd"]:
                print(C_DIM + "template: " + C_OFF + e["template"])
            if e["desc"]:
                print(e["desc"])
            if e["note"]:
                print(C_DIM + "note: " + C_OFF + e["note"])
            if e["tags"]:
                print(C_YEL + " ".join("#" + t for t in e["tags"]) + C_OFF)
            meta = " ".join(x for x in (e.get("created", "")[:10], e.get("host", "")) if x)
            if meta:
                print(C_DIM + "saved " + meta + C_OFF)
            return 0
    return 1


def finish(text, args, entry_cmd=None):
    """Fill placeholders, then decide what to do with the command. Writes 'action\\ncommand' to --out."""
    can_ask = interactive() and (sys.stdout.isatty() or bool(args.widget))
    final = fill_placeholders(text) if can_ask else text
    action = "print"
    if args.widget:
        action = "insert"
    elif can_ask and args.out:
        say(color(C_GRN, "→ ") + color(C_BOLD, final))
        on_prompt = "put on prompt" if args.shell == "zsh" else "add to history (↑ to edit)"
        extra = "   s save" if entry_cmd is None and args.offer_save else ""
        ans = ask("[Enter] %s   r run   c copy   p print%s   q quit" % (on_prompt, extra), "").strip().lower()
        if ans.startswith("q"):
            return 1
        if ans.startswith("r"):
            action = "run"
        elif ans.startswith("c"):
            where = copy_to_clipboard(final)
            say(("Copied via " + where) if where else "No clipboard tool found.")
            action = "history"
        elif ans.startswith("p"):
            action = "print"
        elif ans.startswith("s") and extra:
            note = ask("Note (optional)", "")
            ns = argparse.Namespace(cmd=text, note=note, shell=args.shell)
            cmd_add(ns)
            action = "insert"
        else:
            action = "insert"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(action + "\n" + final + "\n")
        if action == "print":
            print(final)
    else:
        print(final)
    return 0


def cmd_how(args):
    if args.edit:
        ensure_store()
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        return subprocess.call(shlex.split(editor) + [STORE])
    entries = load()
    if args.ask:
        return ai_ask(args, entries)
    if not entries:
        say("Your cheatsheet is empty. Run a command, then type `save`.")
        return 1
    words = " ".join(args.words)
    terms = words.lower().split()
    newest_first = sorted(entries, key=lambda e: e.get("created", ""), reverse=True)
    cands = search(entries, terms) if terms else newest_first
    if not cands:
        say("Nothing matches '%s'. Try fewer words, or: how --ask \"%s\"" % (words, words))
        return 1
    if args.list or not interactive() or not (sys.stdout.isatty() or args.widget):
        for e in cands:
            print(e["cmd"])
        return 0
    if args.rm:
        chosen = pick(cands, words, prompt="delete> ", multi=True)
        if not chosen:
            return 1
        for e in chosen:
            say("  " + label(e))
        if ask("Delete %d entr%s? [y/N]" % (len(chosen), "y" if len(chosen) == 1 else "ies"), "n").lower() != "y":
            return 1
        ids = {e["id"] for e in chosen}
        rewrite([e for e in entries if e["id"] not in ids])
        autocommit("delete %d entries" % len(ids))
        say("Deleted. A backup of the previous file is in commands.jsonl.bak")
        return 0
    if len(cands) == 1 and terms:
        chosen = cands
        if cands[0]["title"]:
            say(color(C_CYAN, cands[0]["title"]))
    else:
        chosen = pick(cands, words if have_fzf() else "")
    if not chosen:
        return 1
    e = chosen[0]
    text = e["template"] if e["template"] and PLACEHOLDER.search(e["template"]) else e["cmd"]
    return finish(text, args, entry_cmd=e["cmd"])


def ai_ask(args, entries):
    import platform
    items = []
    for e in entries[-1500:]:
        items.append({"id": e["id"], "title": e["title"], "cmd": mask(e["template"] or e["cmd"])[0],
                      "tags": e["tags"], "desc": mask(e["desc"] or e["note"])[0]})
    q = mask(args.ask)[0]
    user = json.dumps({"question": q, "os": platform.system(), "shell": args.shell or os.path.basename(os.environ.get("SHELL", "")),
                       "cheatsheet": items}, ensure_ascii=False)
    schema = {"type": "object", "additionalProperties": False, "required": ["matches", "suggestion", "explanation"],
              "properties": {"matches": {"type": "array", "items": {"type": "string"}},
                             "suggestion": {"type": "string"}, "explanation": {"type": "string"}}}
    say(color(C_DIM, "Asking Claude (%s)..." % MODEL))
    try:
        res = call_claude(ASK_SYSTEM, user, schema, max_tokens=4000)
    except RuntimeError as err:
        say("cheats: %s" % err)
        return 1
    by_id = {e["id"]: e for e in entries}
    found = [by_id[i] for i in res.get("matches", []) if i in by_id]
    if res.get("explanation"):
        say(color(C_DIM, res["explanation"]))
    if found:
        chosen = found[:1] if len(found) == 1 else pick(found)
        if not chosen:
            return 1
        e = chosen[0]
        text = e["template"] if e["template"] and PLACEHOLDER.search(e["template"]) else e["cmd"]
        return finish(text, args, entry_cmd=e["cmd"])
    sug = (res.get("suggestion") or "").strip()
    if not sug:
        say("Claude found nothing for that.")
        return 1
    say(color(C_YEL, "Not from your cheatsheet (suggested by Claude, check it before running):"))
    args.offer_save = True
    return finish(sug, args, entry_cmd=None)


def cmd_tidy(args):
    entries = load()
    todo = [e for e in entries if args.all or not e.get("tidied")]
    if args.limit:
        todo = todo[: args.limit]
    if not todo:
        say("Nothing to tidy: every entry already has a title. Use --all to redo them.")
        return 0
    payload, masked = [], 0
    for e in todo:
        c, n1 = mask(e["cmd"])
        nt, n2 = mask(e["note"])
        masked += n1 + n2
        payload.append({"id": e["id"], "cmd": c, "note": nt})
    if args.dry_run:
        say("Would send %d entr%s to %s (%d secret%s masked):" % (len(payload), "y" if len(payload) == 1 else "ies",
                                                                  MODEL, masked, "" if masked == 1 else "s"))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        say("cheat-tidy: set ANTHROPIC_API_KEY first (see README).")
        return 1
    say("%d entr%s to tidy; %d secret%s masked before sending. Preview with: cheat-tidy --dry-run" % (
        len(payload), "y" if len(payload) == 1 else "ies", masked, "" if masked == 1 else "s"))
    if not args.yes and ask("Send them to Claude (%s)? [y/N]" % MODEL, "n").lower() != "y":
        return 1
    schema = {"type": "object", "additionalProperties": False, "required": ["entries"], "properties": {"entries": {
        "type": "array", "items": {"type": "object", "additionalProperties": False,
                                   "required": ["id", "title", "description", "tags", "template"],
                                   "properties": {"id": {"type": "string"}, "title": {"type": "string"},
                                                  "description": {"type": "string"},
                                                  "tags": {"type": "array", "items": {"type": "string"}},
                                                  "template": {"type": "string"}}}}}}
    by_id = {e["id"]: e for e in entries}
    done = 0
    for start in range(0, len(payload), args.batch):
        batch = payload[start:start + args.batch]
        say(color(C_DIM, "  batch %d-%d..." % (start + 1, start + len(batch))))
        try:
            res = call_claude(TIDY_SYSTEM, json.dumps({"entries": batch}, ensure_ascii=False), schema)
        except RuntimeError as err:
            say("cheat-tidy: %s" % err)
            break
        for r in res.get("entries", []):
            e = by_id.get(r.get("id"))
            if not e:
                continue
            e["title"] = r.get("title", "").strip()
            e["desc"] = r.get("description", "").strip()
            e["tags"] = [t.strip().lower() for t in r.get("tags", []) if t.strip()][:6]
            tpl = r.get("template", "").strip()
            e["template"] = tpl if tpl and tpl != e["cmd"] else ""
            e["tidied"] = True
            done += 1
        rewrite(entries)  # save progress after every batch
    if done:
        autocommit("cheat-tidy: %d entries" % done)
    say(color(C_GRN, "Tidied %d entr%s." % (done, "y" if done == 1 else "ies")))
    return 0 if done else 1


def cmd_mask(args):
    text = sys.stdin.read()
    out, n = mask(text)
    sys.stdout.write(out)
    say("(%d masked)" % n)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="cheats.py", description="Command cheatsheet engine (used by save / how / cheat-tidy).")
    sub = p.add_subparsers(dest="sub")

    a = sub.add_parser("add", help="add a command")
    a.add_argument("--cmd", required=True)
    a.add_argument("--note", default="")
    a.add_argument("--shell", default="")

    r = sub.add_parser("recent", help="pick recent successful commands from the session log")
    r.add_argument("--log")
    r.add_argument("--history", help="fallback file of recent history lines (no exit codes)")
    r.add_argument("-n", type=int, default=1)
    r.add_argument("--out", required=True)

    h = sub.add_parser("how", help="search the cheatsheet")
    h.add_argument("words", nargs="*")
    h.add_argument("--ask", help="ask Claude in plain English")
    h.add_argument("--list", action="store_true", help="just print matching commands")
    h.add_argument("--rm", action="store_true", help="delete entries")
    h.add_argument("--edit", action="store_true", help="open the store in $EDITOR")
    h.add_argument("--out", help="(used by the shell wrapper)")
    h.add_argument("--shell", default="")
    h.add_argument("--widget", action="store_true", help="(used by the key binding)")
    h.set_defaults(offer_save=False)

    s = sub.add_parser("show", help="show one entry (fzf preview)")
    s.add_argument("id")

    t = sub.add_parser("tidy", help="add titles, descriptions, tags and templates with Claude")
    t.add_argument("--all", action="store_true", help="redo entries that were already tidied")
    t.add_argument("--dry-run", action="store_true", help="show exactly what would be sent, send nothing")
    t.add_argument("-y", "--yes", action="store_true", help="don't ask for confirmation")
    t.add_argument("--limit", type=int, default=0)
    t.add_argument("--batch", type=int, default=25)

    sub.add_parser("mask", help="mask secrets in stdin (for checking)")

    args = p.parse_args(argv)
    funcs = {"add": cmd_add, "recent": cmd_recent, "how": cmd_how, "show": cmd_show, "tidy": cmd_tidy, "mask": cmd_mask}
    if args.sub not in funcs:
        p.print_help()
        return 2
    try:
        return funcs[args.sub](args)
    except KeyboardInterrupt:
        say("")
        return 130


if __name__ == "__main__":
    sys.exit(main())
