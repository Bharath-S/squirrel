#!/bin/sh
# install.sh - install save / how / squirrel-tidy for bash and/or zsh.
#
#   ./install.sh                 detect your shell from $SHELL
#   ./install.sh --shell zsh     or bash, or both
#   ./install.sh --git           also make ~/squirrel a git repo
#   ./install.sh --uninstall     remove the lines from your rc files (keeps your saved commands)
#
# Env: SQUIRREL_HOME (where the scripts go, default ~/.local/share/squirrel)
#      SQUIRREL_DIR  (where your commands live, default ~/squirrel)
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
DEST=${SQUIRREL_HOME:-$HOME/.local/share/squirrel}
# A custom store folder from before the rename (CHEATS_DIR) stays where it is.
STORE_DIR=${SQUIRREL_DIR:-${CHEATS_DIR:-$HOME/squirrel}}
BEGIN='# >>> squirrel (save/how) >>>'
END='# <<< squirrel (save/how) <<<'
LEGACY_BEGIN='# >>> cheats (save/how) >>>'
LEGACY_END='# <<< cheats (save/how) <<<'

want_shell=""
do_git=0
uninstall=0
while [ $# -gt 0 ]; do
  case "$1" in
    --shell) want_shell=$2; shift ;;
    --shell=*) want_shell=${1#--shell=} ;;
    --git) do_git=1 ;;
    --uninstall) uninstall=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "install.sh: unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$want_shell" ]; then
  want_shell=$(basename "${SHELL:-sh}")
fi
case "$want_shell" in
  bash) shells="bash" ;;
  zsh) shells="zsh" ;;
  both) shells="bash zsh" ;;
  *) echo "Couldn't tell your shell from \$SHELL ($want_shell). Use --shell bash|zsh|both." >&2; exit 2 ;;
esac

rc_for() {
  case "$1" in
    zsh) echo "${ZDOTDIR:-$HOME}/.zshrc" ;;
    bash) echo "$HOME/.bashrc" ;;
  esac
}

strip_block() {  # remove our block (and the one from before the rename) from file $1
  [ -f "$1" ] || return 0
  for marks in "$BEGIN|$END" "$LEGACY_BEGIN|$LEGACY_END"; do
    b=${marks%%|*}; e=${marks#*|}
    if grep -qF "$b" "$1"; then
      tmp="$1.squirrel.tmp"
      awk -v b="$b" -v e="$e" '$0==b{skip=1;next} $0==e{skip=0;next} !skip' "$1" > "$tmp"
      cat "$tmp" > "$1" && rm -f "$tmp"
      echo "Removed old lines from $1"
    fi
  done
}

# Before 1.0 this project was called "cheats". Move that setup over to squirrel.
migrate_from_cheats() {
  old_store=$HOME/cheats
  old_home=${CHEATS_HOME:-$HOME/.local/share/cheats-tool}
  cache=${XDG_CACHE_HOME:-$HOME/.cache}

  # saved commands: ~/cheats -> ~/squirrel (a custom CHEATS_DIR is kept in place)
  if [ -z "${CHEATS_DIR-}" ] && [ -d "$old_store" ] && [ "$old_store" != "$STORE_DIR" ]; then
    if [ -d "$STORE_DIR" ] && [ ! -s "$STORE_DIR/commands.jsonl" ]; then
      rm -f "$STORE_DIR/commands.jsonl"
      rmdir "$STORE_DIR" 2>/dev/null || true   # only if nothing else is in it
    fi
    if [ -e "$STORE_DIR" ]; then
      echo "Both $old_store and $STORE_DIR have saved commands, so neither was moved. To merge them:" >&2
      echo "  cat $old_store/commands.jsonl >> $STORE_DIR/commands.jsonl && rm -r $old_store" >&2
    else
      mv "$old_store" "$STORE_DIR"
      echo "Moved your saved commands from $old_store to $STORE_DIR"
    fi
  fi

  # remembered placeholder values
  if [ -f "$cache/cheats/state.json" ] && [ ! -f "$cache/squirrel/state.json" ]; then
    mkdir -p "$cache/squirrel"
    mv "$cache/cheats/state.json" "$cache/squirrel/state.json"
  fi
  rmdir "$cache/cheats" 2>/dev/null || true

  # the old program files (only the files the old installer put there)
  if [ -d "$old_home" ] && [ "$old_home" != "$DEST" ]; then
    rm -f "$old_home/cheats.sh" "$old_home/cheats.py"
    rm -rf "$old_home/__pycache__"
    rmdir "$old_home" 2>/dev/null && echo "Removed the old program in $old_home"
  fi

  # rc files: drop the old block and rename CHEATS_* settings to SQUIRREL_*
  for rc in "$(rc_for zsh)" "$(rc_for bash)"; do
    [ -f "$rc" ] || continue
    strip_block "$rc" >/dev/null
    if grep -q 'CHEATS_' "$rc"; then
      sed 's/CHEATS_/SQUIRREL_/g' "$rc" > "$rc.squirrel.tmp"
      cat "$rc.squirrel.tmp" > "$rc" && rm -f "$rc.squirrel.tmp"
      echo "Renamed CHEATS_* settings to SQUIRREL_* in $rc"
    fi
  done
  return 0
}

if [ "$uninstall" = 1 ]; then
  for s in $shells; do strip_block "$(rc_for "$s")"; done
  echo "Your saved commands in $STORE_DIR were left alone. The program is in $DEST (delete it if you like)."
  exit 0
fi

# ---- requirements
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' 2>/dev/null; then
  echo "Python 3.8 or newer is needed." >&2
  echo "  macOS:  xcode-select --install   (or: brew install python)" >&2
  echo "  Ubuntu: sudo apt install python3" >&2
  exit 1
fi
if command -v fzf >/dev/null 2>&1; then
  echo "fzf found: $(command -v fzf)"
else
  echo "fzf not found. Everything still works with numbered lists, but fzf is much nicer:"
  echo "  macOS: brew install fzf      Ubuntu: sudo apt install fzf"
fi

migrate_from_cheats

# ---- copy files (same layout as the repo: bin/, squirrel/, shell/)
if [ "$HERE" != "$DEST" ]; then
  mkdir -p "$DEST/bin" "$DEST/squirrel" "$DEST/shell"
  cp "$HERE/bin/squirrel" "$DEST/bin/"
  cp "$HERE"/squirrel/*.py "$DEST/squirrel/"
  cp "$HERE/shell/squirrel.sh" "$DEST/shell/"
fi
chmod +x "$DEST/bin/squirrel"
echo "Installed to $DEST"

# ---- store
mkdir -p "$STORE_DIR"
[ -f "$STORE_DIR/commands.jsonl" ] || : > "$STORE_DIR/commands.jsonl"
echo "Your commands will be saved in $STORE_DIR/commands.jsonl"
if [ "$do_git" = 1 ] && [ ! -d "$STORE_DIR/.git" ]; then
  if command -v git >/dev/null 2>&1; then
    git -C "$STORE_DIR" init -q
    printf '*.bak\n.commands.*.tmp\n' > "$STORE_DIR/.gitignore"
    git -C "$STORE_DIR" add .gitignore commands.jsonl
    git -C "$STORE_DIR" commit -q -m "Start cheatsheet" >/dev/null 2>&1 ||
      echo "(git repo created; set git user.name/user.email before committing)"
    echo "Made $STORE_DIR a git repo (add a remote to sync it between machines)."
  else
    echo "git not found; skipped --git."
  fi
fi

# ---- rc files
for s in $shells; do
  rc=$(rc_for "$s")
  touch "$rc"
  strip_block "$rc" >/dev/null
  {
    echo "$BEGIN"
    echo "export SQUIRREL_HOME=\"$DEST\""
    [ "$STORE_DIR" != "$HOME/squirrel" ] && echo "export SQUIRREL_DIR=\"$STORE_DIR\""
    echo "[ -f \"\$SQUIRREL_HOME/shell/squirrel.sh\" ] && . \"\$SQUIRREL_HOME/shell/squirrel.sh\""
    echo "$END"
  } >> "$rc"
  echo "Added squirrel to $rc"
done

if [ "$(uname -s)" = Darwin ] && echo "$shells" | grep -q bash; then
  echo "Note (macOS bash): login shells read ~/.bash_profile; make sure it sources ~/.bashrc."
fi
echo
echo "Done. Open a new terminal (or run: source $(rc_for "$(echo $shells | cut -d' ' -f1)")), then try:"
echo "  ls -la        # any command"
echo "  save          # saves it"
echo "  how ls        # finds it"
