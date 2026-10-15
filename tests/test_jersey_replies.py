"""Tests for the actual over-the-air Jersey reply text without radio hardware."""
import ast
from pathlib import Path
import unittest


class JerseyReplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[1] / "command_handlers.py").read_text(encoding="utf-8")
        ast.parse(cls.source)

    def test_old_brand_removed_from_reply_handlers(self):
        self.assertNotIn("TC² BBS", self.source)

    def test_jersey_menu_and_quick_help(self):
        for text in ("THE SITDOWN BBS", "The Playbook", "The Social Club", "The Backroom", "Fuggedaboutit"):
            with self.subTest(text=text):
                self.assertIn(text, self.source)


if __name__ == "__main__":
    unittest.main()
