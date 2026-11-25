import unittest

from squirrel.masking import MASK, mask


class MaskTest(unittest.TestCase):
    def assertMasked(self, text, secret):
        out, n = mask(text)
        self.assertNotIn(secret, out)
        self.assertIn(MASK, out)
        self.assertGreater(n, 0)

    def test_known_token_formats(self):
        for token in ("sk-ant-abcdefghijklmnopqrstuv", "ghp_" + "a" * 36, "AKIAABCDEFGHIJKLMNOP",
                      "xoxb-1234567890-abcdef", "github_pat_" + "b" * 30):
            with self.subTest(token=token):
                self.assertMasked("curl -H x " + token, token)

    def test_secret_assignments_and_flags(self):
        self.assertMasked("export GITHUB_TOKEN=abc123", "abc123")
        self.assertMasked("mytool --password hunter2 run", "hunter2")
        self.assertMasked("mysql -u root -phunter2 db", "hunter2")
        self.assertMasked("curl -u alice:hunter2 https://x", "hunter2")
        self.assertMasked("git clone https://alice:hunter2@example.com/r.git", "hunter2")
        self.assertMasked("curl -H 'Authorization: Bearer abc.def'", "abc.def")

    def test_long_random_string(self):
        token = "aB3dE5fG7hJ9kL1mN3pQ5rS7tU9vW1xY3z"
        self.assertMasked("deploy " + token, token)

    def test_ordinary_commands_untouched(self):
        for cmd in ("adb -s emulator-5554 install -r app.apk", "git log --oneline --graph --all",
                    "docker run -p 8080:80 nginx", "ls /usr/local/share/very_long_directory_name_here"):
            with self.subTest(cmd=cmd):
                self.assertEqual(mask(cmd), (cmd, 0))


if __name__ == "__main__":
    unittest.main()
