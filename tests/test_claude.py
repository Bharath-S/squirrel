import io
import json
import unittest
from pathlib import Path

from squirrel.claude import FALLBACK_BETA, ClaudeClient, ClaudeError, parse_response
from squirrel.config import Config


def config(**kw):
    base = dict(store_dir=Path("/tmp/x"), cache_dir=Path("/tmp/y"), api_key="test-key")
    base.update(kw)
    return Config(**base)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ClaudeClientTest(unittest.TestCase):
    def test_request_shape_with_fallback_and_effort(self):
        body, headers = ClaudeClient(config(effort="low")).build_request("sys", "hi", {"type": "object"}, 100)
        self.assertEqual(body["model"], "claude-opus-5-5")
        self.assertEqual(body["fallbacks"], "default")
        self.assertEqual(body["output_config"]["effort"], "low")
        self.assertEqual(headers["anthropic-beta"], FALLBACK_BETA)
        self.assertEqual(headers["x-api-key"], "test-key")

    def test_no_fallback_when_disabled_or_unsupported(self):
        for cfg in (config(fallback=False), config(model="claude-haiku-5-5")):
            body, headers = ClaudeClient(cfg).build_request("s", "u", {}, 1)
            self.assertNotIn("fallbacks", body)
            self.assertNotIn("anthropic-beta", headers)

    def test_request_json_parses_text(self):
        reply = {"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"ok": true}'}]}
        sent = []

        def opener(req, timeout):
            sent.append(json.loads(req.data))
            return FakeResponse(json.dumps(reply).encode())

        self.assertEqual(ClaudeClient(config(), opener).request_json("s", "u", {}), {"ok": True})
        self.assertEqual(sent[0]["messages"], [{"role": "user", "content": "u"}])

    def test_missing_key(self):
        with self.assertRaises(ClaudeError):
            ClaudeClient(config(api_key="")).request_json("s", "u", {})

    def test_refusal_and_truncation(self):
        for stop in ("refusal", "max_tokens"):
            with self.assertRaises(ClaudeError):
                parse_response({"stop_reason": stop, "content": []})

    def test_api_key_not_in_repr(self):
        self.assertNotIn("test-key", repr(config()))


if __name__ == "__main__":
    unittest.main()
