import os
import tempfile
import unittest

from squirrel import history


class SelectTest(unittest.TestCase):
    def test_newest_success_and_skipped_failure(self):
        records = [("0", "ls"), ("0", "pwd"), ("1", "false")]
        self.assertEqual(history.select(records, 1), (["pwd"], ("1", "false")))

    def test_dedupes_and_limits(self):
        records = [("0", "a"), ("0", "b"), ("0", "a"), ("0", "c")]
        self.assertEqual(history.select(records, 3)[0], ["c", "a", "b"])

    def test_only_first_failure_reported(self):
        records = [("2", "old-fail"), ("0", "ok"), ("1", "new-fail")]
        self.assertEqual(history.select(records, 1), (["ok"], ("1", "new-fail")))


class RecentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "log")
        self.hist = os.path.join(self.tmp.name, "hist")

    def tearDown(self):
        self.tmp.cleanup()

    def test_log_skips_self_commands_and_restores_newlines(self):
        with open(self.log, "w") as f:
            f.write("0\tfor i in 1 2\x1fdo echo $i; done\n0\tsave\n0\thow adb\n")
        found = history.recent(self.log, None, 1)
        self.assertEqual(found.commands, ["for i in 1 2\ndo echo $i; done"])
        self.assertTrue(found.from_log)

    def test_falls_back_to_history(self):
        open(self.log, "w").close()
        with open(self.hist, "w") as f:
            f.write("  git status\nsave\n")
        found = history.recent(self.log, self.hist, 1)
        self.assertEqual(found.commands, ["git status"])
        self.assertFalse(found.from_log)


if __name__ == "__main__":
    unittest.main()
