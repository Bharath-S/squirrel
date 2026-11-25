"""Mask secrets before anything is sent to Claude.

Only text that goes over the network is masked. The store keeps commands
exactly as they were saved. Check the masking with:  bin/squirrel mask < some-file
"""
from __future__ import annotations

import re
from typing import List, Pattern, Tuple

MASK = "<secret>"

RULES: List[Tuple[Pattern[str], str]] = [
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
    (re.compile(r"(?i)((?:x-api-key|api-key|x-auth-token|private-token|x-access-token)\s*:\s*)[^\s'\"]+"),
     r"\1" + MASK),
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


def _looks_random(token: str) -> bool:
    return (any(c.isdigit() for c in token) and any(c.islower() for c in token)
            and any(c.isupper() for c in token))


def mask(text: str) -> Tuple[str, int]:
    """Return (masked_text, number_of_replacements)."""
    total = 0
    for rx, repl in RULES:
        text, n = rx.subn(repl, text)
        total += n

    def replace_long(m: re.Match[str]) -> str:
        nonlocal total
        if _looks_random(m.group(0)):
            total += 1
            return MASK
        return m.group(0)

    return _LONG_TOKEN.sub(replace_long, text), total
