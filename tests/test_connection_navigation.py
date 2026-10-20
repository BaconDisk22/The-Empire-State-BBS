"""Connection navigation must remain local, visible, and session-preserving."""
import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sitdown_desktop import SitdownApp, THEME


class ConnectionNavigationTests(unittest.TestCase):
    def test_navigation_reveals_controls_and_preserves_session_for_every_state(self):
        cases = [
            (False, None, False, 'BBS STOPPED'),
            (True, None, False, 'DEMO'),
            (False, SimpleNamespace(running=True, ready=False, radio_state=None), False, 'STARTING'),
            (False, SimpleNamespace(running=True, ready=True, radio_state=None), False, 'radio link UNVERIFIED'),
            (False, SimpleNamespace(running=True, ready=True, radio_state='RECONNECTING'), False, 'RECONNECTING'),
            (False, SimpleNamespace(running=True, ready=True, radio_state='CONNECTED'), False, 'RF delivery UNVERIFIED'),
            (False, None, True, 'USB MISSING'),
        ]
        for demo, supervisor, waiting, expected in cases:
            with self.subTest(expected=expected):
                app = SitdownApp.__new__(SitdownApp)
                app.root = Mock()
                app.connection_panel = Mock()
                app.connection_address = Mock()
                app.colors = THEME
                app.demo = Mock(get=Mock(return_value=demo))
                app.connection = Mock(get=Mock(return_value='tcp'))
                app.address = Mock(get=Mock(return_value='radio.local'))
                app.radio_health = Mock()
                app.supervisor = supervisor
                app.waiting_for_usb = waiting
                app.restart_at = 123
                app.retry_count = 3
                with patch('sitdown_desktop.messagebox') as dialogs, \
                     patch('sitdown_desktop.ServerSupervisor') as start_session, \
                     patch('sitdown_desktop.check_tcp_target') as probe, \
                     patch.object(app, 'start') as start, \
                     patch.object(app, 'stop') as stop:
                    app.show_radio()
                    app.show_radio()
                    self.assertFalse(dialogs.mock_calls)
                    start_session.assert_not_called()
                    probe.assert_not_called()
                    start.assert_not_called()
                    stop.assert_not_called()
                self.assertEqual(app.root.deiconify.call_count, 2)
                self.assertEqual(app.root.lift.call_count, 2)
                app.connection_panel.configure.assert_called_with(highlightbackground=THEME['highlight'])
                self.assertEqual(app.connection_address.focus_set.call_count, 2)
                self.assertIn(expected, app.radio_health.set.call_args.args[0])
                self.assertIs(app.supervisor, supervisor)
                self.assertEqual((app.restart_at, app.retry_count), (123, 3))
                app.address.set.assert_not_called()
                app.connection.set.assert_not_called()

    @unittest.skipUnless(os.environ.get("EMPIRE_GUI_TESTS") == "1",
                         "Set EMPIRE_GUI_TESTS=1 with a working Tk display (enabled in CI)")
    def test_real_navigation_button_focuses_existing_dashboard_control(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        with tempfile.TemporaryDirectory() as temp, \
             patch('sitdown_desktop.DATA', Path(temp)), \
             patch('sitdown_desktop.CONFIG', Path(temp) / 'launcher.json'), \
             patch('sitdown_desktop.DesktopStore'), \
             patch('sitdown_desktop.messagebox') as dialogs, \
             patch('sitdown_desktop.ServerSupervisor') as start_session:
            app = SitdownApp(root)
            root.update_idletasks()

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            button = next(w for w in descendants(root)
                          if isinstance(w, tk.Button) and w.cget('text') == 'THE EMPIRE CONNECTION')
            original_widgets = set(descendants(root))
            app.address.set('radio.local')
            app.connection.set('tcp')
            root.withdraw()
            button.invoke()
            root.update_idletasks()
            # Tk remembers the requested focus even when the OS keeps another app active.
            self.assertEqual(root.focus_lastfor(), app.connection_address)
            self.assertEqual(root.state(), 'normal')
            self.assertTrue(app.connection_address.winfo_viewable())
            self.assertEqual(app.connection_panel.cget('highlightbackground'), THEME['highlight'])
            self.assertIn('BBS STOPPED', app.radio_health.get())
            button.invoke()
            self.assertEqual(set(descendants(root)), original_widgets)
            self.assertEqual(app.address.get(), 'radio.local')
            self.assertFalse(dialogs.mock_calls)
            start_session.assert_not_called()
