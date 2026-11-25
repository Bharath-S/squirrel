import tempfile
import unittest
from pathlib import Path

from squirrel import placeholders


class PlaceholderTest(unittest.TestCase):
    def test_find_unique_with_defaults(self):
        self.assertEqual(placeholders.find("ssh <host> -p <port:22> <host>"), [("host", None), ("port", "22")])

    def test_substitute_leaves_empty_values(self):
        self.assertEqual(placeholders.substitute("a <x> <y>", {"x": "1", "y": ""}), "a 1 <y>")

    def test_fill_remembers_values_but_not_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = placeholders.Memory(Path(tmp) / "state.json")
            answers = {"device": "pixel", "api_token": "s3cret"}
            asked = []

            def ask(name, default):
                asked.append((name, default))
                return answers[name]

            out = placeholders.fill("adb -s <device> push --t <api_token>", ask, memory)
            self.assertEqual(out, "adb -s pixel push --t s3cret")
            self.assertEqual(memory.load(), {"device": "pixel"})

            placeholders.fill("adb -s <device>", ask, memory)
            self.assertEqual(asked[-1], ("device", "pixel"))

    def test_no_placeholders_asks_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = placeholders.Memory(Path(tmp) / "state.json")
            self.assertEqual(placeholders.fill("ls", lambda n, d: self.fail("asked"), memory), "ls")


if __name__ == "__main__":
    unittest.main()
