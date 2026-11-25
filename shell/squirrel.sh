# squirrel.sh - `save`, `how` and `squirrel-tidy` for bash and zsh.
# Source this from ~/.bashrc or ~/.zshrc (install.sh does it for you).
# The heavy lifting is in the Python package, run through bin/squirrel
# (Python 3.8+, standard library only).

# Only for interactive shells.
case $- in *i*) ;; *) return 0 2>/dev/null ;; esac

if [ -z "${SQUIRREL_HOME-}" ]; then
  if [ -n "${ZSH_VERSION-}" ]; then
    eval 'SQUIRREL_HOME=${${(%):-%x}:A:h:h}'
  elif [ -n "${BASH_VERSION-}" ]; then
    SQUIRREL_HOME=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
  fi
fi

_squirrel_shell=bash
[ -n "${ZSH_VERSION-}" ] && _squirrel_shell=zsh

# Per-session log of "exit-status<TAB>command" (newlines inside a command become \x1f).
_squirrel_log="${TMPDIR:-/tmp}"
_squirrel_log="${_squirrel_log%/}/squirrel-${USER:-$(id -un)}-$$.log"
( umask 077; : > "$_squirrel_log" ) 2>/dev/null
_squirrel_count=0

_squirrel_py() { command "${SQUIRREL_PYTHON:-python3}" "$SQUIRREL_HOME/bin/squirrel" "$@"; }

_squirrel_record() {  # $1 = exit status, $2 = command line
  local c="$2"
  case "$c" in ''|save|save\ *|how|how\ *|squirrel-tidy*|_squirrel_*) return 0 ;; esac
  c=${c//$'\n'/$'\x1f'}
  printf '%s\t%s\n' "$1" "$c" >> "$_squirrel_log" 2>/dev/null
  _squirrel_count=$((_squirrel_count + 1))
  if [ "$_squirrel_count" -ge 400 ]; then            # keep the log small
    _squirrel_count=0
    tail -n 200 "$_squirrel_log" > "$_squirrel_log.t" 2>/dev/null && command mv -f "$_squirrel_log.t" "$_squirrel_log"
  fi
}

# Read a value with line editing, pre-filled with $_squirrel_val. $1 = prompt.
_squirrel_edit() {
  if [ -n "${ZSH_VERSION-}" ]; then
    vared -p "$1" _squirrel_val
  else
    if [ "${BASH_VERSINFO[0]:-3}" -ge 4 ]; then
      read -e -r -i "$_squirrel_val" -p "$1" _squirrel_val
    else  # bash 3.2 (macOS default bash) has no -i: show the value, Enter keeps it
      local _old=$_squirrel_val
      [ -n "$_old" ] && printf '%s\n' "$_old" >&2
      read -e -r -p "$1" _squirrel_val || return 1
      [ -n "$_squirrel_val" ] || _squirrel_val=$_old
    fi
  fi
}

_squirrel_to_history() {
  if [ -n "${ZSH_VERSION-}" ]; then print -s -- "$1"; else history -s -- "$1"; fi
}

# --------------------------------------------------------------------------- hooks
if [ -n "${ZSH_VERSION-}" ]; then
  _squirrel_preexec() { _squirrel_pending=$1; _squirrel_has_pending=1; }
  _squirrel_precmd() {
    local s=$?
    if [ -n "${_squirrel_has_pending-}" ]; then
      _squirrel_has_pending=
      _squirrel_record "$s" "$_squirrel_pending"
    fi
    return $s
  }
  # precmd goes first so it sees the real exit status before other hooks run
  precmd_functions=(_squirrel_precmd ${precmd_functions:#_squirrel_precmd})
  preexec_functions=(${preexec_functions:#_squirrel_preexec} _squirrel_preexec)
else
  _squirrel_first=1
  _squirrel_bash_hook() {
    local s=$? h n
    h=$(HISTTIMEFORMAT= builtin history 1)
    h="${h#"${h%%[![:space:]]*}"}"
    n="${h%%[!0-9]*}"
    h="${h#"$n"}"; h="${h#\*}"; h="${h#"${h%%[![:space:]]*}"}"
    if [ -n "${_squirrel_first-}" ]; then
      _squirrel_first=; _squirrel_lastn=$n          # first prompt: line comes from an old session
    elif [ -n "$n" ] && [ "$n" != "${_squirrel_lastn-}" ]; then
      _squirrel_lastn=$n
      _squirrel_record "$s" "$h"
    fi
    return $s
  }
  case ";${PROMPT_COMMAND-};" in
    *";_squirrel_bash_hook;"*) ;;
    *) PROMPT_COMMAND="_squirrel_bash_hook${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;
  esac
fi

# --------------------------------------------------------------------------- save
save() {
  local n=1 tmp hist line note rc=0 _squirrel_val
  case "${1-}" in
    -h|--help)
      cat >&2 <<'EOF'
save          save the last command that succeeded
save N        pick from the last N successful commands (Tab marks several in fzf)
save -c CMD   save CMD itself
While saving you can edit the command, e.g. turn a device id into <device> or <port:8080>.
EOF
      return 0 ;;
    -c) shift; tmp=$(mktemp "${TMPDIR:-/tmp}/squirrel.XXXXXX") || return 1
        printf '%s\n' "$*" > "$tmp" ;;
    '') ;;
    *[!0-9]*) echo "save: expected a number, -c CMD or --help" >&2; return 2 ;;
    *) n=$1 ;;
  esac
  if [ -z "${tmp-}" ]; then
    tmp=$(mktemp "${TMPDIR:-/tmp}/squirrel.XXXXXX") || return 1
    hist=$(mktemp "${TMPDIR:-/tmp}/squirrel.XXXXXX") || return 1
    fc -ln -$((n + 30)) 2>/dev/null > "$hist"
    _squirrel_py recent --log "$_squirrel_log" --history "$hist" -n "$n" --out "$tmp" || rc=$?
    command rm -f "$hist"
    if [ $rc -ne 0 ]; then command rm -f "$tmp"; return $rc; fi
  fi
  while IFS= read -r line <&3; do
    [ -n "$line" ] || continue
    _squirrel_val=${line//$'\x1f'/$'\n'}
    case "$_squirrel_val" in
      *$'\n'*) printf 'Command:\n%s\n' "$_squirrel_val" >&2 ;;
      *) _squirrel_edit "Command: " || { echo >&2; rc=130; break; } ;;
    esac
    line=$_squirrel_val
    [ -n "$line" ] || continue
    _squirrel_val=
    _squirrel_edit "Note (optional): " || { echo >&2; rc=130; break; }
    note=$_squirrel_val
    _squirrel_py add --cmd "$line" --note "$note" --shell "$_squirrel_shell" || rc=$?
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
  out=$(mktemp "${TMPDIR:-/tmp}/squirrel.XXXXXX") || return 1
  _squirrel_py how --out "$out" --shell "$_squirrel_shell" "$@" || rc=$?
  if [ $rc -eq 0 ] && [ -s "$out" ]; then
    { IFS= read -r action; cmd=$(command cat); } < "$out"
    case "$action" in
      run)
        _squirrel_to_history "$cmd"
        printf '$ %s\n' "$cmd" >&2
        command rm -f "$out"
        eval "$cmd"
        return $? ;;
      insert)
        if [ -n "${ZSH_VERSION-}" ]; then
          print -z -- "$cmd"
        else
          _squirrel_to_history "$cmd"
          echo "(press the Up arrow to edit or run it)" >&2
        fi ;;
      history) _squirrel_to_history "$cmd" ;;
    esac
  fi
  command rm -f "$out"
  return $rc
}

squirrel-tidy() { _squirrel_py tidy "$@"; }

# --------------------------------------------------------------------------- key binding (Ctrl-G)
# Searches using what is already typed on the prompt line and replaces it with the result.
# Set SQUIRREL_KEY to change the key (zsh: '^G', bash: '\C-g'), or SQUIRREL_NO_KEY=1 to disable.
if [ -z "${SQUIRREL_NO_KEY-}" ]; then
  if [ -n "${ZSH_VERSION-}" ]; then
    _squirrel_widget() {
      local out action cmd
      out=$(mktemp "${TMPDIR:-/tmp}/squirrel.XXXXXX") || return 1
      zle -I
      _squirrel_py how --widget --out "$out" --shell zsh ${=BUFFER} < /dev/tty
      if [ -s "$out" ]; then
        { IFS= read -r action; cmd=$(command cat); } < "$out"
        BUFFER=$cmd; CURSOR=${#BUFFER}
      fi
      command rm -f "$out"
      zle reset-prompt
    }
    zle -N _squirrel_widget
    bindkey "${SQUIRREL_KEY:-^G}" _squirrel_widget
  elif [ "${BASH_VERSINFO[0]:-0}" -ge 4 ]; then
    _squirrel_bash_widget() {
      local out action cmd
      out=$(mktemp "${TMPDIR:-/tmp}/squirrel.XXXXXX") || return 1
      # shellcheck disable=SC2086
      _squirrel_py how --widget --out "$out" --shell bash $READLINE_LINE < /dev/tty
      if [ -s "$out" ]; then
        { IFS= read -r action; cmd=$(command cat); } < "$out"
        READLINE_LINE=$cmd; READLINE_POINT=${#cmd}
      fi
      command rm -f "$out"
    }
    bind -x "\"${SQUIRREL_KEY:-\\C-g}\": _squirrel_bash_widget" 2>/dev/null
  fi
fi

# Remove session logs left behind by shells that have exited (older than a day).
find "${TMPDIR:-/tmp}" -maxdepth 1 -name "squirrel-${USER:-x}-*.log" -mtime +1 -exec rm -f {} + 2>/dev/null
