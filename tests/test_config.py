import os
import tempfile
import unittest
from pathlib import Path

from squirrel.config import DEFAULT_MODEL, Config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)

    def tearDown(self):
        os.environ["HOME"] = self._old_home
        self.tmp.cleanup()

    def test_defaults(self):
        cfg = Config.from_env({})
        self.assertEqual(cfg.store_dir, self.home / "squirrel")
        self.assertEqual(cfg.model, DEFAULT_MODEL)
        self.assertTrue(cfg.use_fzf)

    def test_explicit_dir(self):
        self.assertEqual(Config.from_env({"SQUIRREL_DIR": "~/x"}).store_dir, self.home / "x")


if __name__ == "__main__":
    unittest.main()
