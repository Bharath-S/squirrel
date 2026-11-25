# squirrel 🐿️

Stash away the shell commands you keep looking up, and dig them up again in seconds.

```sh
$ adb -s emulator-5554 install -r app.apk
$ save                      # saves the last command that worked
$ how adb inst              # finds it again: partial words, any order
```

Works in **bash** and **zsh** on macOS and Linux. Needs only Python 3.8+.
Your commands stay in a plain text file on your machine.

## Install

```sh
git clone https://github.com/Bharath-S/squirrel.git
cd squirrel
sh install.sh
```

Then open a new terminal.

[fzf](https://github.com/junegunn/fzf) is optional but recommended
(`brew install fzf` or `sudo apt install fzf`). Without it you get numbered lists.

## Use it

| Command | What it does |
|---|---|
| `save` | Save the last command that succeeded. You can edit it and add a note first. |
| `save 10` | Pick from your last 10 successful commands. |
| `save -c 'CMD'` | Save a command without running it. |
| `how WORDS` | Search everything you saved. |
| `how` | Browse everything. |
| **Ctrl-G** | Search using what you've typed on the prompt, and replace it with the result (zsh, or bash 4+). |
| `how --rm WORDS` | Delete entries (a backup is kept). |
| `how --edit` | Open your cheatsheet in `$EDITOR`. |

Run `save --help` or `how --help` for every option.

When you pick a command, press:

- **Enter** to put it on your prompt (zsh) or into history, so ↑ brings it back (bash)
- **r** to run it
- **c** to copy it
- **p** to print it

### Placeholders

Write `<name>` or `<name:default>` in a saved command:

```sh
save -c 'adb -s <device> install -r <apk:app-debug.apk>'
```

When you use it, `how` asks for each value and remembers your last answer.
Values for names like `token` or `password` are never remembered.

## Optional: Claude features

These need an [Anthropic API key](https://console.anthropic.com):
`export ANTHROPIC_API_KEY=sk-ant-...`

```sh
squirrel-tidy                  # add titles, tags and <placeholders> to new entries
how --ask "remove an app from the phone"   # search in plain English
```

**Your secrets are masked before anything is sent.** API keys, tokens,
passwords and similar values become `<secret>`. Run `squirrel-tidy --dry-run` to
see exactly what would be sent. Nothing is sent unless you run one of these
two commands.

## Sync between machines

Your cheatsheet is `~/squirrel/commands.jsonl`, one JSON object per line, so it
works well with git:

```sh
sh install.sh --git                   # makes ~/squirrel a git repo
export SQUIRREL_GIT_AUTOCOMMIT=1        # in your rc file: commit after each change
```

Then add a remote and push or pull as you like. Save secrets as placeholders
(`<api_token>`), not real values, if you sync.

## Settings

Set these in `~/.zshrc` or `~/.bashrc`.

| Variable | Default | Meaning |
|---|---|---|
| `SQUIRREL_DIR` | `~/squirrel` | Where your commands are stored |
| `SQUIRREL_GIT_AUTOCOMMIT` | off | `1` = git commit after each change |
| `SQUIRREL_KEY` | Ctrl-G | Key for the prompt search (zsh: `^G`, bash: `\C-g`) |
| `SQUIRREL_NO_KEY` | off | `1` = don't bind a key |
| `SQUIRREL_NO_FZF` | off | `1` = use numbered lists |
| `SQUIRREL_MODEL` | `claude-opus-5-5` | Claude model, e.g. `claude-haiku-5-5` to spend less |
| `SQUIRREL_EFFORT` | model default | `low`, `medium` or `high` |
| `SQUIRREL_NO_FALLBACK` | off | `1` = don't retry a mistaken refusal on another model |
| `SQUIRREL_PYTHON` | `python3` | Python to use |

## Install options and uninstall

```sh
sh install.sh --shell bash      # or zsh, or both (default: your $SHELL)
sh install.sh --uninstall       # removes the rc lines; keeps your saved commands
```

The installer copies the tool to `~/.local/share/squirrel` and adds a
4-line block to your rc file. Running it again updates the tool in place.

On macOS with bash, make sure `~/.bash_profile` sources `~/.bashrc`.

**Upgrading from `cheats`?** Run `sh install.sh` from this repo. It moves
`~/cheats` to `~/squirrel`, renames `CHEATS_*` settings in your rc files to
`SQUIRREL_*`, and removes the old program. `cheat-tidy` is now `squirrel-tidy`.

## How it works

A small shell hook records each command's exit code, so `save` skips commands
that failed. The rest is a Python package that uses only the standard library.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the code layout and how to run the tests.

## License

[MIT](LICENSE)
