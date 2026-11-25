# Contributing

Bug reports and pull requests are welcome.

## Ground rules

- **Standard library only.** No pip dependencies, so `sh install.sh` is the whole install.
- **Python 3.8+**, and both **bash** (including macOS bash 3.2) and **zsh**.
- **Never change a saved command without asking.** Masking applies only to text sent to Claude.

## Layout

```
bin/squirrel          launcher the shell functions call
shell/squirrel.sh     save / how / squirrel-tidy, the exit-code hook and the Ctrl-G binding
squirrel/
  cli.py              argument parsing and dispatch
  commands.py         one handler per subcommand
  config.py           settings from environment variables
  store.py            Entry and the commands.jsonl store
  search.py           matching and ranking
  history.py          recent successful commands for `save`
  placeholders.py     <name> / <name:default> filling
  picker.py           fzf or numbered list
  clipboard.py        pbcopy, wl-copy, xclip, xsel, clip.exe, OSC 52
  masking.py          secret masking before anything is sent
  claude.py           Claude API client (urllib)
  prompts.py          system prompts and output schemas
  ui.py               terminal prompts, colors and labels
tests/                unittest suite
```

## Before you open a pull request

```sh
python3 -m unittest discover -s tests -t .
pipx run ruff check .        # optional locally; CI runs it
shellcheck install.sh        # optional locally; CI runs it
```

Test the shell side by hand in both bash and zsh: `save`, `save 5`, `how WORDS`, and Ctrl-G.
To try a change without touching your real install, use a throwaway home:

```sh
env -u SQUIRREL_HOME HOME="$(mktemp -d)" sh install.sh --shell zsh
```
