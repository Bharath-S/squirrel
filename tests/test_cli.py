"""End-to-end: run bin/squirrel in a subprocess against a temporary store."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / "bin" / "squirrel"


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = dict(os.environ, SQUIRREL_DIR=self.tmp.name, XDG_CACHE_HOME=self.tmp.name,
                        SQUIRREL_NO_FZF="1", ANTHROPIC_API_KEY="")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, stdin=""):
        return subprocess.run([sys.executable, str(LAUNCHER), *args], input=stdin, env=self.env,
                              cwd=self.tmp.name, capture_output=True, text=True)

    def test_add_then_list(self):
        self.assertEqual(self.run_cli("add", "--cmd", "adb install -r app.apk").returncode, 0)
        self.assertIn("Already", self.run_cli("add", "--cmd", "adb install -r app.apk").stderr)
        out = self.run_cli("how", "--list", "adb", "inst")
        self.assertEqual(out.stdout, "adb install -r app.apk\n")

    def test_no_match(self):
        self.run_cli("add", "--cmd", "ls")
        self.assertEqual(self.run_cli("how", "--list", "zzz").returncode, 1)

    def test_mask(self):
        out = self.run_cli("mask", stdin="export API_TOKEN=abc\n")
        self.assertEqual(out.stdout, "export API_TOKEN=<secret>\n")

    def test_tidy_dry_run_sends_nothing(self):
        self.run_cli("add", "--cmd", "curl -H 'Authorization: Bearer xyz' https://api")
        out = self.run_cli("tidy", "--dry-run")
        self.assertEqual(out.returncode, 0)
        self.assertNotIn("xyz", out.stdout)

    def test_version_and_help(self):
        self.assertIn("squirrel", self.run_cli("--version").stdout)
        self.assertEqual(self.run_cli().returncode, 2)


if __name__ == "__main__":
    unittest.main()
