import unittest
from radio_health import radio_health_label


class RadioHealthTests(unittest.TestCase):
    def test_demo(self):
        self.assertIn("DEMO", radio_health_label(True, False, False))
    def test_missing_usb(self):
        self.assertIn("USB MISSING", radio_health_label(False, True, True, False))
    def test_stopped(self):
        self.assertIn("STOPPED", radio_health_label(False, False, False))
    def test_starting(self):
        self.assertIn("STARTING", radio_health_label(False, True, False))
    def test_ready_still_unverified(self):
        self.assertIn("UNVERIFIED", radio_health_label(False, True, True))


if __name__ == "__main__":
    unittest.main()
