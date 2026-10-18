import json
import unittest

from grapevine_protocol import encode_send, decode_send, SessionDeduplicator


class GrapevineProtocolTests(unittest.TestCase):
    def test_roundtrip(self):
        line = encode_send("a" * 32, "!ABCDEF12", "Subject", "Hello")
        self.assertEqual(json.loads(decode_send(line))["recipient"], "!abcdef12")

    def test_duplicate_rejected(self):
        seen = SessionDeduplicator()
        line = encode_send("a" * 32, "!abcdef12", "Subject", "Hello")
        seen.accept(line)
        with self.assertRaises(ValueError):
            seen.accept(line)

    def test_invalid_commands(self):
        line = encode_send("a" * 32, "!abcdef12", "Subject", "Hello")
        with self.assertRaises(ValueError):
            decode_send(line.replace("grapevine.send", "other.command"))
        with self.assertRaises(ValueError):
            decode_send(line.strip()[:-1] + ', "extra":true}')
        with self.assertRaises(ValueError):
            encode_send("../wrong", "!abcdef12", "Subject", "Hello")


if __name__ == "__main__":
    unittest.main()
