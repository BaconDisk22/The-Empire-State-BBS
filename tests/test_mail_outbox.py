import tempfile
import unittest

from mail_outbox import LocalOutbox, validate_message


class LocalOutboxTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(validate_message(" !A1b2C3d4 ", "Hi", "Hello"), "!a1b2c3d4")
        for recipient in ("", "12345678", "!not-a-node", "!123456789"):
            with self.assertRaises(ValueError):
                validate_message(recipient, "Hi", "Hello")
        with self.assertRaises(ValueError):
            validate_message("!1234abcd", "Hi", "")

    def test_persistence_and_no_automatic_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = LocalOutbox(directory)
            record = outbox.create("!1234abcd", "Subject", "Hello")
            self.assertEqual(outbox.load(record["id"])["status"], "draft")
            outbox.transition(record["id"], "queued")
            outbox.transition(record["id"], "sending")
            outbox.transition(record["id"], "unknown", "TCP dropped; delivery unverified")
            self.assertEqual(outbox.load(record["id"])["status"], "unknown")
            with self.assertRaises(ValueError):
                outbox.transition(record["id"], "sending")

    def test_invalid_transition_and_id(self):
        with tempfile.TemporaryDirectory() as directory:
            outbox = LocalOutbox(directory)
            record = outbox.create("!1234abcd", "Subject", "Hello")
            with self.assertRaises(ValueError):
                outbox.transition(record["id"], "acknowledged")
            with self.assertRaises(ValueError):
                outbox.load("../escape")


if __name__ == "__main__":
    unittest.main()
