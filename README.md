# cheats: save and find the commands you keep looking up

Three commands for bash (Ubuntu) and zsh (macOS):

| Command | What it does |
|---|---|
| `save` | Saves the last command that **succeeded** to your cheatsheet. You can edit it first, for example turning a device id into `<device>`, and add a note. |
| `how WORDS` | Searches everything you saved: titles, descriptions, tags, notes and the command itself. Words can be partial and in any order, so `how adb inst` finds `adb install -r app.apk`. |
| `cheat-tidy` | Optional. Asks Claude to add a title, description, tags and a `<placeholder>` template to new entries. Secrets are masked before anything is sent. |

You also get **Ctrl-G**: type a few words on the prompt, press Ctrl-G, and the line is replaced with the command you pick.

## Install

You need **Python 3.8+**, which is already there on Ubuntu. On a Mac, run `xcode-select --install` if `python3` isn't available. **fzf** is recommended but optional: without it you get numbered lists.

```sh
# Ubuntu
sudo apt install fzf
# macOS
brew install fzf

cd /path/to/cheats-tool     # the folder with install.sh
sh install.sh               # picks bash or zsh from $SHELL
sh install.sh --git         # same, and makes ~/cheats a git repo
```

Then open a new terminal. The installer:

- copies `cheats.sh` and `cheats.py` to `~/.local/share/cheats-tool`
- creates `~/cheats/commands.jsonl`
- adds a 4-line block to `~/.zshrc` or `~/.bashrc`. Running it again won't add the block twice.

Use `--shell bash|zsh|both` to pick the shell yourself. `./install.sh --uninstall` removes the block and keeps your saved commands.

## Using it

```sh
adb -s emulator-5554 install -r app.apk
save                  # Command: adb -s emulator-5554 install -r app.apk   <- edit it if you like
                      # Note (optional): reinstall the debug build
save 10               # choose from your last 10 successful commands (Tab marks several in fzf)
save -c 'git log --oneline --graph --all'   # save a command without running it

how adb inst          # one match: goes straight to it. Several: opens fzf with your words typed in
how                   # browse everything, with a preview pane (Ctrl-/ toggles it)
how --list docker     # just print matching commands (also what happens in a pipe)
how --rm docker       # delete entries (a backup goes to commands.jsonl.bak)
how --edit            # open the store in $EDITOR
```

**Placeholders.** Write `<name>` or `<name:default>` in a saved command. When you pick it, `how` asks for each value and remembers the last one you typed, except for names that look like secrets (token, password, key).

**After picking**, you choose what happens:

| Key | zsh | bash |
|---|---|---|
| Enter | puts the command on your prompt, ready to edit or run | adds it to history: press ↑ to get it |
| `r` | runs it (and adds it to history) | same |
| `c` | copies it (pbcopy, wl-copy, xclip, or the terminal's OSC 52) | same |
| `p` | prints it | same |

In bash, **Ctrl-G** is the way to get a command straight onto the prompt line.

**Failed commands are skipped.** The shell records each command's exit code, so `save` takes the last command that succeeded and tells you when it skipped a failed one. In a brand-new shell with no commands yet, it falls back to your history, where exit codes aren't known.

## Claude features (optional)

Both features need an API key from console.anthropic.com. Put this in `~/.zshrc` or `~/.bashrc`:

```sh
export ANTHROPIC_API_KEY=sk-ant-...
```

```sh
cheat-tidy --dry-run    # shows exactly what would be sent (secrets already masked); sends nothing
cheat-tidy              # tidies entries that don't have a title yet, after you confirm
cheat-tidy --all        # redo every entry
how --ask "uninstall an app from the phone"
```

- `cheat-tidy` never changes your original command. It adds `title`, `desc`, `tags` and `template`, and `how` uses the template when it has placeholders.
- `how --ask` sends your question and your masked cheatsheet. Claude points to your own entries first. If none fit, it suggests a command, labelled as not from your cheatsheet, and you can press `s` to save it.
- **Masking** replaces these with `<secret>` before sending: API tokens (`sk-…`, `ghp_…`, `github_pat_…`, `xox…`, AWS `AKIA…`, Google `AIza…`, JWTs), `NAME=value` where the name contains password, secret, token or key, `--password/--token/--api-key VALUE`, `Authorization:` and `X-Api-Key:` headers, `user:pass@` in URLs, `mysql -p…`, `sshpass -p`, `curl -u user:pass`, private key blocks, and long random-looking strings. You can check it yourself with `python3 ~/.local/share/cheats-tool/cheats.py mask < some-file`.
- The model is Claude Opus 5.5 by default. Set `CHEATS_MODEL` to change it, for example `claude-sonnet-5-5` or `claude-haiku-5-5`, which cost less. On models that support it, the request turns on Anthropic's server-side fallback, so a request that Claude's safety filter declines by mistake is retried on another model. Set `CHEATS_NO_FALLBACK=1` to turn that off.

Masking only applies to what gets sent to Claude. Your store keeps the commands exactly as you saved them, so if you sync `~/cheats` with git, save secrets as placeholders (`<api_token>`) rather than real values.

## Syncing between the Mac and Ubuntu

`~/cheats` is plain text, one JSON object per line, so it works well in git:

```sh
./install.sh --git
cd ~/cheats && git remote add origin git@github.com:YOU/cheats.git && git push -u origin HEAD
export CHEATS_GIT_AUTOCOMMIT=1   # in your rc file: commit after every save/tidy/delete
```

Pull and push yourself, or add a cron job.

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `CHEATS_DIR` | `~/cheats` | where `commands.jsonl` lives |
| `CHEATS_GIT_AUTOCOMMIT` | off | `1` = git commit after each change |
| `CHEATS_KEY` | `^G` (zsh), `\C-g` (bash) | key for the prompt-line search |
| `CHEATS_NO_KEY` | off | `1` = don't bind a key |
| `CHEATS_NO_FZF` | off | `1` = use numbered lists even if fzf is installed |
| `CHEATS_MODEL` | `claude-opus-5-5` | model for `cheat-tidy` and `how --ask` |
| `CHEATS_EFFORT` | model default | `low`, `medium` or `high` |
| `CHEATS_PYTHON` | `python3` | Python interpreter to use |

## Files

- `cheats.sh`: shell functions. It holds the exit-code hook (`PROMPT_COMMAND` in bash, `precmd`/`preexec` in zsh), `save`, `how`, `cheat-tidy` and the Ctrl-G binding.
- `cheats.py`: the engine, standard library only. It handles store read/write, search and ranking, fzf and numbered pickers, placeholders, clipboard, secret masking and the Claude API calls. Run `python3 cheats.py --help` for its subcommands.
- `install.sh`: the installer and uninstaller.
- Store entry: `{"id", "cmd", "note", "title", "desc", "tags", "template", "created", "host", "shell", "tidied"}`.
