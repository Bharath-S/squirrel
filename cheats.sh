# cheats.sh - `save`, `how` and `cheat-tidy` for bash and zsh.
# Source this from ~/.bashrc or ~/.zshrc (install.sh does it for you).
# The heavy lifting is in cheats.py (Python 3, standard library only).

# Only for interactive shells.
case $- in *i*) ;; *) return 0 2>/dev/null ;; esac

if [ -z "${CHEATS_HOME-}" ]; then
  if [ -n "${ZSH_VERSION-}" ]; then
    eval 'CHEATS_HOME=${${(%):-%x}:A:h}'
  elif [ -n "${BASH_VERSION-}" ]; then
    CHEATS_HOME=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  fi
fi

_cheats_shell=bash
[ -n "${ZSH_VERSION-}" ] && _cheats_shell=zsh

# Per-session log of "exit-status<TAB>command" (newlines inside a command become \x1f).
_cheats_log="${TMPDIR:-/tmp}"
_cheats_log="${_cheats_log%/}/cheats-${USER:-$(id -un)}-$$.log"
( umask 077; : > "$_cheats_log" ) 2>/dev/null
_cheats_count=0

_cheats_py() { command "${CHEATS_PYTHON:-python3}" "$CHEATS_HOME/cheats.py" "$@"; }

_cheats_record() {  # $1 = exit status, $2 = command line
  local c="$2"
  case "$c" in ''|save|save\ *|how|how\ *|cheat-tidy*|_cheats_*) return 0 ;; esac
  c=${c//$'\n'/$'\x1f'}
  printf '%s\t%s\n' "$1" "$c" >> "$_cheats_log" 2>/dev/null
  _cheats_count=$((_cheats_count + 1))
  if [ "$_cheats_count" -ge 400 ]; then            # keep the log small
    _cheats_count=0
    tail -n 200 "$_cheats_log" > "$_cheats_log.t" 2>/dev/null && command mv -f "$_cheats_log.t" "$_cheats_log"
  fi
}

# Read a value with line editing, pre-filled with $_cheats_val. $1 = prompt.
_cheats_edit() {
  if [ -n "${ZSH_VERSION-}" ]; then
    vared -p "$1" _cheats_val
  else
    if [ "${BASH_VERSINFO[0]:-3}" -ge 4 ]; then
      read -e -r -i "$_cheats_val" -p "$1" _cheats_val
    else  # bash 3.2 (macOS default bash) has no -i: show the value, Enter keeps it
      local _old=$_cheats_val
      [ -n "$_old" ] && printf '%s\n' "$_old" >&2
      read -e -r -p "$1" _cheats_val || return 1
      [ -n "$_cheats_val" ] || _cheats_val=$_old
    fi
  fi
}

_cheats_to_history() {
  if [ -n "${ZSH_VERSION-}" ]; then print -s -- "$1"; else history -s -- "$1"; fi
}

# --------------------------------------------------------------------------- hooks
if [ -n "${ZSH_VERSION-}" ]; then
  _cheats_preexec() { _cheats_pending=$1; _cheats_has_pending=1; }
  _cheats_precmd() {
    local s=$?
    if [ -n "${_cheats_has_pending-}" ]; then
      _cheats_has_pending=
      _cheats_record "$s" "$_cheats_pending"
    fi
    return $s
  }
  # precmd goes first so it sees the real exit status before other hooks run
  precmd_functions=(_cheats_precmd ${precmd_functions:#_cheats_precmd})
  preexec_functions=(${preexec_functions:#_cheats_preexec} _cheats_preexec)
else
  _cheats_first=1
  _cheats_bash_hook() {
    local s=$? h n
    h=$(HISTTIMEFORMAT= builtin history 1)
    h="${h#"${h%%[![:space:]]*}"}"
    n="${h%%[!0-9]*}"
    h="${h#"$n"}"; h="${h#\*}"; h="${h#"${h%%[![:space:]]*}"}"
    if [ -n "${_cheats_first-}" ]; then
      _cheats_first=; _cheats_lastn=$n          # first prompt: line comes from an old session
    elif [ -n "$n" ] && [ "$n" != "${_cheats_lastn-}" ]; then
      _cheats_lastn=$n
      _cheats_record "$s" "$h"
    fi
    return $s
  }
  case ";${PROMPT_COMMAND-};" in
    *";_cheats_bash_hook;"*) ;;
    *) PROMPT_COMMAND="_cheats_bash_hook${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;
  esac
fi

# --------------------------------------------------------------------------- save
save() {
  local n=1 tmp hist line note rc=0 _cheats_val
  case "${1-}" in
    -h|--help)
      cat >&2 <<'EOF'
save          save the last command that succeeded
save N        pick from the last N successful commands (Tab marks several in fzf)
save -c CMD   save CMD itself
While saving you can edit the command, e.g. turn a device id into <device> or <port:8080>.
EOF
      return 0 ;;
    -c) shift; tmp=$(mktemp "${TMPDIR:-/tmp}/cheats.XXXXXX") || return 1
        printf '%s\n' "$*" > "$tmp" ;;
    '') ;;
    *[!0-9]*) echo "save: expected a number, -c CMD or --help" >&2; return 2 ;;
    *) n=$1 ;;
  esac
  if [ -z "${tmp-}" ]; then
    tmp=$(mktemp "${TMPDIR:-/tmp}/cheats.XXXXXX") || return 1
    hist=$(mktemp "${TMPDIR:-/tmp}/cheats.XXXXXX") || return 1
    fc -ln -$((n + 30)) 2>/dev/null > "$hist"
    _cheats_py recent --log "$_cheats_log" --history "$hist" -n "$n" --out "$tmp" || rc=$?
    command rm -f "$hist"
    if [ $rc -ne 0 ]; then command rm -f "$tmp"; return $rc; fi
  fi
  while IFS= read -r line <&3; do
    [ -n "$line" ] || continue
    _cheats_val=${line//$'\x1f'/$'\n'}
    case "$_cheats_val" in
      *$'\n'*) printf 'Command:\n%s\n' "$_cheats_val" >&2 ;;
      *) _cheats_edit "Command: " || { echo >&2; rc=130; break; } ;;
    esac
    line=$_cheats_val
    [ -n "$line" ] || continue
    _cheats_val=
    _cheats_edit "Note (optional): " || { echo >&2; rc=130; break; }
    note=$_cheats_val
    _cheats_py add --cmd "$line" --note "$note" --shell "$_cheats_shell" || rc=$?
  done 3< "$tmp"
  command rm -f "$tmp"
  return $rc
}

# --------------------------------------------------------------------------- how
how() {
  case "${1-}" in
    -h|--help)
      cat >&2 <<'EOF'
how                 browse everything (fzf: type fragments in any order)
how WORDS...        search titles, descriptions, tags, notes and the command itself
how --ask "TEXT"    ask Claude in plain English (needs ANTHROPIC_API_KEY)
how --list WORDS    just print matching commands
how --rm [WORDS]    delete entries        how --edit   open the store in $EDITOR
After you pick: fill in <placeholders>, then Enter = put on prompt (zsh) / into history (bash),
r = run, c = copy, p = print.   Key binding: Ctrl-G searches from the prompt line.
EOF
      return 0 ;;
  esac
  local out action cmd rc=0
  out=$(mktemp "${TMPDIR:-/tmp}/cheats.XXXXXX") || return 1
  _cheats_py how --out "$out" --shell "$_cheats_shell" "$@" || rc=$?
  if [ $rc -eq 0 ] && [ -s "$out" ]; then
    { IFS= read -r action; cmd=$(command cat); } < "$out"
    case "$action" in
      run)
        _cheats_to_history "$cmd"
        printf '$ %s\n' "$cmd" >&2
        command rm -f "$out"
        eval "$cmd"
        return $? ;;
      insert)
        if [ -n "${ZSH_VERSION-}" ]; then
          print -z -- "$cmd"
        else
          _cheats_to_history "$cmd"
          echo "(press the Up arrow to edit or run it)" >&2
        fi ;;
      history) _cheats_to_history "$cmd" ;;
    esac
  fi
  command rm -f "$out"
  return $rc
}

cheat-tidy() { _cheats_py tidy "$@"; }

# --------------------------------------------------------------------------- key binding (Ctrl-G)
# Searches using what is already typed on the prompt line and replaces it with the result.
# Set CHEATS_KEY to change the key (zsh: '^G', bash: '\C-g'), or CHEATS_NO_KEY=1 to disable.
if [ -z "${CHEATS_NO_KEY-}" ]; then
  if [ -n "${ZSH_VERSION-}" ]; then
    _cheats_widget() {
      local out action cmd
      out=$(mktemp "${TMPDIR:-/tmp}/cheats.XXXXXX") || return 1
      zle -I
      _cheats_py how --widget --out "$out" --shell zsh ${=BUFFER} < /dev/tty
      if [ -s "$out" ]; then
        { IFS= read -r action; cmd=$(command cat); } < "$out"
        BUFFER=$cmd; CURSOR=${#BUFFER}
      fi
      command rm -f "$out"
      zle reset-prompt
    }
    zle -N _cheats_widget
    bindkey "${CHEATS_KEY:-^G}" _cheats_widget
  elif [ "${BASH_VERSINFO[0]:-0}" -ge 4 ]; then
    _cheats_bash_widget() {
      local out action cmd
      out=$(mktemp "${TMPDIR:-/tmp}/cheats.XXXXXX") || return 1
      # shellcheck disable=SC2086
      _cheats_py how --widget --out "$out" --shell bash $READLINE_LINE < /dev/tty
      if [ -s "$out" ]; then
        { IFS= read -r action; cmd=$(command cat); } < "$out"
        READLINE_LINE=$cmd; READLINE_POINT=${#cmd}
      fi
      command rm -f "$out"
    }
    bind -x "\"${CHEATS_KEY:-\\C-g}\": _cheats_bash_widget" 2>/dev/null
  fi
fi

# Remove session logs left behind by shells that have exited (older than a day).
find "${TMPDIR:-/tmp}" -maxdepth 1 -name "cheats-${USER:-x}-*.log" -mtime +1 -exec rm -f {} + 2>/dev/null
