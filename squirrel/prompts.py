"""System prompts and output schemas for the two Claude features."""

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

TIDY_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["entries"],
    "properties": {"entries": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "title", "description", "tags", "template"],
        "properties": {
            "id": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "template": {"type": "string"},
        },
    }}},
}

ASK_SYSTEM = """You help someone find a shell command in their personal cheatsheet. You get their question, \
their OS and shell, and the cheatsheet entries (id, title, command, tags, description). Secrets were replaced with \
<secret>. Return:
- matches: ids of the entries that answer the question, best first, at most 5. Empty if none really fits.
- suggestion: only when no entry fits, one command that does what they asked on their OS and shell, using \
<placeholders> for values they must fill in. Otherwise an empty string.
- explanation: one short sentence about the suggestion or the best match."""

ASK_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["matches", "suggestion", "explanation"],
    "properties": {
        "matches": {"type": "array", "items": {"type": "string"}},
        "suggestion": {"type": "string"},
        "explanation": {"type": "string"},
    },
}
