import json
import tempfile
import unittest
from pathlib import Path

from squirrel.store import Entry, Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "sub" / "commands.jsonl"
        self.warnings = []
        self.store = Store(self.path, warn=self.warnings.append)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_missing_file(self):
        self.assertEqual(self.store.load(), [])

    def test_append_and_load_round_trip(self):
        e = Entry.new("ls -la", note="list", shell="zsh")
        self.store.append(e)
        [loaded] = self.store.load()
        self.assertEqual(loaded.to_dict(), e.to_dict())

    def test_rewrite_keeps_backup(self):
        self.store.append(Entry.new("one"))
        self.store.rewrite([Entry.new("two")])
        self.assertEqual([e.cmd for e in self.store.load()], ["two"])
        self.assertIn("one", self.store.backup_path.read_text())

    def test_bad_lines_skipped_with_warning(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"cmd": "ok"}\nnot json\n{"note": "no cmd"}\n\n')
        self.assertEqual([e.cmd for e in self.store.load()], ["ok"])
        self.assertEqual(len(self.warnings), 2)

    def test_old_entries_normalized_and_unknown_fields_kept(self):
        e = Entry.from_dict({"cmd": "x", "tags": "oops", "title": 3, "custom": 1})
        self.assertEqual(e.tags, [])
        self.assertEqual(e.title, "")
        self.assertEqual(len(e.id), 12)
        self.assertEqual(e.to_dict()["custom"], 1)
        self.assertEqual(list(e.to_dict())[:2], ["id", "cmd"])

    def test_runnable_prefers_template_with_placeholders(self):
        self.assertEqual(Entry(cmd="adb install a.apk", template="adb install <apk>").runnable, "adb install <apk>")
        self.assertEqual(Entry(cmd="ls", template="ls -la").runnable, "ls")

    def test_file_is_one_json_object_per_line(self):
        self.store.append(Entry.new("a"))
        self.store.append(Entry.new("b"))
        lines = self.path.read_text().splitlines()
        self.assertEqual([json.loads(line)["cmd"] for line in lines], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
