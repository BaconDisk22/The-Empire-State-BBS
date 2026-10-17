import unittest
from unittest.mock import Mock, patch
from sitdown_desktop import SitdownApp


class USBHotplugTests(unittest.TestCase):
    def app(self):
        app = SitdownApp.__new__(SitdownApp)
        app.demo = Mock()
        app.demo.get.return_value = False
        app.connection = Mock()
        app.connection.get.return_value = "serial"
        app.address = Mock()
        app.address.get.return_value = ""
        app.supervisor = None
        app.waiting_for_usb = False
        app.auto_restart = Mock()
        app.auto_restart.get.return_value = False
        app.status = Mock()
        app.log = Mock()
        app.last_serial_ports = ()
        return app

    @patch("sitdown_desktop.available_serial_ports", return_value=["/dev/tty.usb0"])
    def test_new_single_port_autoselect(self, _ports):
        app = self.app()
        app.watch_serial_ports()
        app.address.set.assert_called_once_with("/dev/tty.usb0")

    @patch("sitdown_desktop.available_serial_ports", return_value=[])
    def test_removed_selected_port_alerts(self, _ports):
        app = self.app()
        app.last_serial_ports = ("/dev/tty.usb0",)
        app.address.get.return_value = "/dev/tty.usb0"
        app.watch_serial_ports()
        self.assertIn("USB device removed", app.status.set.call_args.args[0])

    @patch("sitdown_desktop.available_serial_ports", return_value=["/dev/tty.usb0"])
    def test_does_not_overwrite_existing_target(self, _ports):
        app = self.app()
        app.address.get.return_value = "/dev/tty.custom"
        app.watch_serial_ports()
        app.address.set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
