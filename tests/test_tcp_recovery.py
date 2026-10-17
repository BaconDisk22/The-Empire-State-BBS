"""Desktop recovery policy without a Tk display or real radio."""
import unittest
from unittest.mock import Mock, patch
from sitdown_desktop import SitdownApp


def variable(value):
    return Mock(get=Mock(return_value=value))


class RecoveryTests(unittest.TestCase):
    def app(self, enabled=False):
        app = SitdownApp.__new__(SitdownApp)
        app.demo = variable(False)
        app.connection = variable('tcp')
        app.address = variable('10.0.0.76')
        app.auto_restart = variable(enabled)
        app.restart_at = None
        app.retry_count = 0
        app.waiting_for_usb = False
        app.last_serial_scan = 100
        app.last_serial_ports = None
        app.supervisor = None
        for attr in ('root', 'log', 'status', 'radio_health', 'uptime', 'node_count', 'start'):
            setattr(app, attr, Mock())
        return app

    def exited(self):
        monitor = Mock(running=False, stopping=False, ready=False, radio_state='UNRESPONSIVE')
        monitor.poll_events.return_value = []
        monitor.process.poll.return_value = 2
        return monitor

    @patch('sitdown_desktop.time.monotonic', return_value=100)
    def test_no_recovery_without_opt_in(self, _clock):
        app = self.app()
        app.supervisor = self.exited()
        app.poll()
        self.assertIsNone(app.restart_at)
        app.start.assert_not_called()

    @patch('sitdown_desktop.time.monotonic', return_value=100)
    def test_retries_back_off_and_are_capped(self, _clock):
        app = self.app(True)
        delays = []
        for _ in range(8):
            app.supervisor = self.exited()
            app.restart_at = None
            app.poll()
            delays.append(app.restart_at - 100)
        self.assertEqual(delays, [2, 4, 8, 16, 32, 60, 60, 60])

    @patch('sitdown_desktop.time.monotonic', return_value=100)
    def test_opt_out_cancels_pending_retry(self, _clock):
        app = self.app(False)
        app.restart_at = 99
        app.poll()
        app.start.assert_not_called()
        self.assertIsNone(app.restart_at)

    @patch('sitdown_desktop.time.monotonic', return_value=100)
    def test_live_process_is_not_replaced(self, _clock):
        app = self.app(True)
        app.supervisor = self.exited()
        app.supervisor.running = True
        app.poll()
        self.assertIsNone(app.restart_at)
        app.start.assert_not_called()

    def test_stop_cancels_pending_recovery(self):
        app = self.app(True)
        app.restart_at = 99
        app.supervisor = Mock()
        monitor = app.supervisor
        app.stop()
        monitor.stop.assert_called_once()
        self.assertIsNone(app.restart_at)
        self.assertIsNone(app.supervisor)

    @patch('sitdown_desktop.messagebox.showinfo')
    @patch('sitdown_desktop.check_tcp_target')
    def test_preflight_cannot_open_competing_connection(self, check, _message):
        app = self.app()
        app.supervisor = Mock(running=True)
        app.check_radio_target()
        check.assert_not_called()
