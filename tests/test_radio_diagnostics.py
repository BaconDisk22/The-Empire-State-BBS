import unittest
from unittest.mock import Mock
from radio_diagnostics import check_serial_target, check_tcp_target


class RadioDiagnosticsTests(unittest.TestCase):
    def test_serial_missing(self):
        self.assertIn("not currently enumerated", check_serial_target("/dev/tty.missing", []))

    def test_serial_found_is_not_link_verified(self):
        self.assertIn("does not verify", check_serial_target("/dev/tty.usb0", ["/dev/tty.usb0"]))

    def test_serial_auto_discovery(self):
        self.assertIn("Available USB ports", check_serial_target("", ["/dev/tty.usb0"]))

    def test_tcp_reachable_does_not_claim_radio(self):
        conn = Mock()
        result = check_tcp_target("radio.local", connector=Mock(return_value=conn))
        self.assertIn("remain unverified", result)
        conn.close.assert_called_once()

    def test_invalid_tcp_port_does_not_dial(self):
        dial = Mock()
        for port in (0, -1, 65536, True, "4403"):
            self.assertIn("valid TCP port", check_tcp_target("radio.local", port=port, connector=dial))
        dial.assert_not_called()

    def test_invalid_tcp_timeout_does_not_dial(self):
        dial = Mock()
        for timeout in (0, -1, 31, True, "slow"):
            self.assertIn("TCP timeout", check_tcp_target("radio.local", timeout=timeout, connector=dial))
        dial.assert_not_called()

    def test_tcp_unreachable(self):
        def fail(*args, **kwargs):
            raise OSError("refused")
        self.assertIn("unreachable", check_tcp_target("radio.local", connector=fail))


if __name__ == "__main__":
    unittest.main()
