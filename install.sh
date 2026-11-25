#!/bin/sh
# install.sh - install save / how / cheat-tidy for bash and/or zsh.
#
#   ./install.sh                 detect your shell from $SHELL
#   ./install.sh --shell zsh     or bash, or both
#   ./install.sh --git           also make ~/cheats a git repo
#   ./install.sh --uninstall     remove the lines from your rc files (keeps your saved commands)
#
# Env: CHEATS_HOME (where the scripts go, default ~/.local/share/cheats-tool)
#      CHEATS_DIR  (where your commands live, default ~/cheats)
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
DEST=${CHEATS_HOME:-$HOME/.local/share/cheats-tool}
STORE_DIR=${CHEATS_DIR:-$HOME/cheats}
BEGIN='# >>> cheats (save/how) >>>'
END='# <<< cheats (save/how) <<<'

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

strip_block() {  # remove our block from file $1
  [ -f "$1" ] || return 0
  if grep -qF "$BEGIN" "$1"; then
    tmp="$1.cheats.tmp"
    awk -v b="$BEGIN" -v e="$END" '$0==b{skip=1;next} $0==e{skip=0;next} !skip' "$1" > "$tmp"
    cat "$tmp" > "$1" && rm -f "$tmp"
    echo "Removed cheats lines from $1"
  fi
}

if [ "$uninstall" = 1 ]; then
  for s in $shells; do strip_block "$(rc_for "$s")"; done
  echo "Your saved commands in $STORE_DIR were left alone. Scripts are in $DEST (delete it if you like)."
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

# ---- copy scripts
mkdir -p "$DEST"
if [ "$HERE" != "$DEST" ]; then
  cp "$HERE/cheats.sh" "$HERE/cheats.py" "$DEST/"
fi
chmod +x "$DEST/cheats.py"
echo "Installed scripts to $DEST"

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
    echo "export CHEATS_HOME=\"$DEST\""
    [ "$STORE_DIR" != "$HOME/cheats" ] && echo "export CHEATS_DIR=\"$STORE_DIR\""
    echo "[ -f \"\$CHEATS_HOME/cheats.sh\" ] && . \"\$CHEATS_HOME/cheats.sh\""
    echo "$END"
  } >> "$rc"
  echo "Added cheats to $rc"
done

if [ "$(uname -s)" = Darwin ] && echo "$shells" | grep -q bash; then
  echo "Note (macOS bash): login shells read ~/.bash_profile; make sure it sources ~/.bashrc."
fi
echo
echo "Done. Open a new terminal (or run: source $(rc_for "$(echo $shells | cut -d' ' -f1)")), then try:"
echo "  ls -la        # any command"
echo "  save          # saves it"
echo "  how ls        # finds it"
