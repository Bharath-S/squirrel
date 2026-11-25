"""A small Claude API client with structured (JSON schema) output.

Uses urllib from the standard library, so the tool needs no pip install.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Tuple

from .config import Config

API_VERSION = "2026-10-21"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that accept the server-side refusal fallback ("fallbacks": "default").
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5",
                             "claude-fable-5-2", "claude-fable-5-1"})
TIMEOUT_SECONDS = 300


class ClaudeError(RuntimeError):
    """Any failure talking to Claude, with a message fit to show the user."""


class ClaudeClient:
    def __init__(self, config: Config, opener: Callable[..., Any] = urllib.request.urlopen) -> None:
        self.config = config
        self._open = opener

    @property
    def model(self) -> str:
        return self.config.model

    def build_request(self, system: str, user: str, schema: Dict[str, Any],
                      max_tokens: int) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """Return (body, headers) for one Messages API call."""
        cfg = self.config
        body: Dict[str, Any] = {
            "model": cfg.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        headers = {"content-type": "application/json", "x-api-key": cfg.api_key,
                   "anthropic-version": API_VERSION}
        if cfg.fallback and cfg.model in FALLBACK_MODELS:
            body["fallbacks"] = "default"
            headers["anthropic-beta"] = FALLBACK_BETA
        if cfg.effort:
            body["output_config"]["effort"] = cfg.effort
        return body, headers

    def request_json(self, system: str, user: str, schema: Dict[str, Any],
                     max_tokens: int = 16000) -> Dict[str, Any]:
        """Send one request and return Claude's answer parsed as JSON."""
        if not self.config.api_key:
            raise ClaudeError("ANTHROPIC_API_KEY is not set (export it in your shell, e.g. in ~/.zshrc).")
        body, headers = self.build_request(system, user, schema, max_tokens)
        req = urllib.request.Request(self.config.api_url, data=json.dumps(body).encode("utf-8"),
                                     headers=headers, method="POST")
        try:
            with self._open(req, timeout=TIMEOUT_SECONDS) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            raise ClaudeError("Claude API error %s: %s" % (e.code, _error_message(e))) from None
        except urllib.error.URLError as e:
            raise ClaudeError("Could not reach the Claude API: %s" % e.reason) from None
        return parse_response(data)


def parse_response(data: Dict[str, Any]) -> Dict[str, Any]:
    stop = data.get("stop_reason")
    if stop == "refusal":
        raise ClaudeError("Claude declined this request.")
    if stop == "max_tokens":
        raise ClaudeError("Claude's answer was cut off (max_tokens); try fewer entries with --batch.")
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    try:
        return json.loads(text)
    except ValueError:
        raise ClaudeError("Claude returned something that isn't JSON:\n" + text[:500]) from None


def _error_message(e: urllib.error.HTTPError) -> str:
    detail = e.read().decode("utf-8", "replace")
    try:
        return json.loads(detail)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return detail
