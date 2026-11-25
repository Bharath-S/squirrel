import unittest

from squirrel.search import newest_first, search, term_score
from squirrel.store import Entry


def entry(cmd, **kw):
    return Entry(cmd=cmd, **kw)


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.adb = entry("adb -s emulator-5554 install -r app.apk", created="2026-01-02")
        self.git = entry("git log --oneline --graph --all", title="Pretty git log", created="2026-01-03")
        self.docker = entry("docker ps -a", tags=["docker"], created="2026-01-01")
        self.entries = [self.adb, self.git, self.docker]

    def test_partial_words_in_any_order(self):
        self.assertEqual(search(self.entries, ["inst", "adb"]), [self.adb])

    def test_every_term_must_match(self):
        self.assertEqual(search(self.entries, ["adb", "docker"]), [])

    def test_title_and_tags_are_searched(self):
        self.assertEqual(search(self.entries, ["pretty"]), [self.git])
        self.assertEqual(search(self.entries, ["docker"]), [self.docker])

    def test_case_insensitive(self):
        self.assertEqual(search(self.entries, ["ADB"]), [self.adb])

    def test_word_start_beats_middle(self):
        self.assertGreater(term_score("log", "git log"), term_score("log", "catalog"))

    def test_newest_first(self):
        self.assertEqual(newest_first(self.entries), [self.git, self.adb, self.docker])


if __name__ == "__main__":
    unittest.main()
