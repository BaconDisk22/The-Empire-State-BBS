import unittest

from sitdown_commands import resolve_shortcut


class SitdownCommandsTest(unittest.TestCase):
    def test_aliases_ignore_case_and_spaces(self):
        self.assertEqual(resolve_shortcut(" /SiTdOwN "), "x")
        self.assertEqual(resolve_shortcut("/MAIL"), "cm")
        self.assertEqual(resolve_shortcut("/socialclub"), "b")

    def test_normal_message_is_unchanged(self):
        self.assertIsNone(resolve_shortcut("Ayyy how you doin?"))
        self.assertIsNone(resolve_shortcut("sm,,recipient,subject,hello"))
        self.assertIsNone(resolve_shortcut("/unknown"))

    def test_do_not_override_text_entry(self):
        state = {"command": "BULLETIN_POST_CONTENT"}
        self.assertIsNone(resolve_shortcut("/fortune", state))
        self.assertEqual(resolve_shortcut("/cancel", state), "x")


if __name__ == "__main__":
    unittest.main()
