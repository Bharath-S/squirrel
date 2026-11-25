"""Search and ranking.

Every search word must match some field. A word scores higher when it starts
a word, and a little when its letters appear in order inside a word
(`inst` matches `install`). Matches in the title and tags count most.
"""
from __future__ import annotations

import re
from typing import List, Sequence

from .store import Entry

FIELD_WEIGHTS = (("title", 3.0), ("tags", 2.5), ("cmd", 2.0), ("template", 2.0), ("desc", 1.0), ("note", 1.0))
_WORD = re.compile(r"[A-Za-z0-9_.-]+")


def _is_subsequence(term: str, word: str) -> bool:
    it = iter(word)
    return all(c in it for c in term)


def term_score(term: str, text: str) -> float:
    i = text.find(term)
    if i >= 0:
        return 1.0 if i == 0 or not text[i - 1].isalnum() else 0.6
    if len(term) >= 3 and any(_is_subsequence(term, w) for w in _WORD.findall(text)):
        return 0.25
    return 0.0


def _field_text(e: Entry, name: str) -> str:
    value = getattr(e, name)
    return (" ".join(value) if isinstance(value, list) else value).lower()


def search(entries: Sequence[Entry], terms: Sequence[str]) -> List[Entry]:
    """Entries that match every term, best first; ties go to the newest."""
    scored = []
    for e in entries:
        texts = [(_field_text(e, name), weight) for name, weight in FIELD_WEIGHTS]
        total = 0.0
        for term in terms:
            best = max(term_score(term.lower(), text) * weight for text, weight in texts)
            if best == 0:
                break
            total += best
        else:
            scored.append((total, e.created, e))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [e for _, _, e in scored]


def newest_first(entries: Sequence[Entry]) -> List[Entry]:
    return sorted(entries, key=lambda e: e.created, reverse=True)
