"""Behaviour of the redesigned desktop UI and its design system."""
import os
import tempfile
import tkinter as tk
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import empire_ui as ui
from desktop_session import DesktopStore
from desktop_views import radio_bytes, relative_time, state_label

GUI = os.environ.get("EMPIRE_GUI_TESTS") == "1"


class PureHelperTests(unittest.TestCase):
    def test_counter_matches_the_payload_that_would_be_sent(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DesktopStore(Path(temp) / "d.db", Path(temp) / "b.db")
            for kind, subject, body in [("mail", "Hi", "Net at 8 — café ☕"),
                                        ("bulletin", " Spaced ", "  body  ")]:
                post = store.create(kind, subject, body, "!a1b2c3d4")
                payload = store.payload(store.get(post))
                self.assertEqual(radio_bytes(kind, subject, body), len(payload.encode("utf-8")))

    def test_every_persisted_state_has_a_human_label(self):
        for state in ("draft", "queued", "sending", "sent", "acknowledged", "failed", "unknown", "received"):
            label, tone = state_label(state)
            self.assertTrue(label and label[0].isupper())
            self.assertIn(tone, ui.TONES)
        self.assertEqual(state_label("sent")[0], "Sent · unconfirmed")
        self.assertEqual(state_label(None)[1], "neutral")

    def test_relative_time_is_conservative(self):
        self.assertEqual(relative_time(1000, 1010), "just now")
        self.assertEqual(relative_time(1000, 1000 + 300), "5 min ago")
        self.assertEqual(relative_time(1000, 1000 + 7200), "2 h ago")
        for bad in (None, "x", True, 0, -5, float("nan"), 999999):
            self.assertEqual(relative_time(bad, 1000), "Unknown")

    def test_humanize_seconds(self):
        self.assertEqual(ui.humanize_seconds("0"), "0s")
        self.assertEqual(ui.humanize_seconds(125), "2m 05s")
        self.assertEqual(ui.humanize_seconds(3 * 3600 + 60), "3h 01m")
        self.assertEqual(ui.humanize_seconds("bad"), "—")

    def test_palettes_share_every_semantic_slot(self):
        self.assertEqual(set(ui._DARK), set(ui._LIGHT))
        for fg, bg, icon in ui.TONES.values():
            self.assertIn(fg, ui._DARK)
            self.assertIn(bg, ui._DARK)
            self.assertIn(icon, ui.ICON)


def bare_app():
    from sitdown_desktop import SitdownApp
    app = SitdownApp.__new__(SitdownApp)
    app.root = Mock()
    app.log = Mock()
    app.toast = Mock()
    app.stop = Mock()
    return app


class AppLogicTests(unittest.TestCase):
    def test_quit_asks_before_stopping_a_running_server(self):
        app = bare_app()
        app.supervisor = Mock(running=True)
        with patch("sitdown_desktop.messagebox.askyesno", return_value=False) as ask:
            app.close()
        ask.assert_called_once()
        app.stop.assert_not_called()
        app.root.destroy.assert_not_called()
        with patch("sitdown_desktop.messagebox.askyesno", return_value=True):
            app.close()
        app.stop.assert_called_once()
        app.root.destroy.assert_called_once()

    def test_quit_without_a_server_does_not_ask(self):
        app = bare_app()
        app.supervisor = None
        with patch("sitdown_desktop.messagebox.askyesno") as ask:
            app.close()
        ask.assert_not_called()
        app.root.destroy.assert_called_once()

    def test_backup_includes_the_packaged_app_data_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            data, root = Path(temp) / "data", Path(temp) / "bundle"
            data.mkdir()
            root.mkdir()
            for name in ("launcher.json", "config.ini", "desktop-state.db", "bulletins.db"):
                (data / name).write_text(name)
            target = Path(temp) / "backup.zip"
            app = bare_app()
            with patch("sitdown_desktop.DATA", data), patch("sitdown_desktop.ROOT", root), \
                 patch("sitdown_desktop.CONFIG", data / "launcher.json"), \
                 patch("sitdown_desktop.filedialog.asksaveasfilename", return_value=str(target)):
                app.backup()
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(sorted(archive.namelist()),
                                 ["bulletins.db", "config.ini", "desktop-state.db", "launcher.json"])


@unittest.skipUnless(GUI, "Set EMPIRE_GUI_TESTS=1 with a working Tk display (enabled in CI)")
class LiveWindowTests(unittest.TestCase):
    def setUp(self):
        from sitdown_desktop import SitdownApp
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        data = Path(self.temp.name)
        patches = [patch("sitdown_desktop.DATA", data),
                   patch("sitdown_desktop.CONFIG", data / "launcher.json"),
                   patch("sitdown_desktop.ROOT", data),
                   patch("sitdown_desktop.ServerSupervisor")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        with patch.object(SitdownApp, "poll"):
            self.app = SitdownApp(self.root)
        self.root.update_idletasks()

    def test_every_page_opens_in_the_main_window(self):
        before = set(self.root.winfo_children())
        for key in self.app.pages:
            self.app.navigate(key)
            self.root.update_idletasks()
            self.assertEqual(self.app.current_page, key)
        self.assertEqual(set(self.root.winfo_children()), before, "no extra windows opened")

    def test_messages_page_shows_new_draft_and_hides_empty_state(self):
        page = self.app.page_objects["messages"]
        self.app.navigate("messages")
        self.root.update_idletasks()
        self.assertTrue(page.empty.winfo_ismapped() or page.empty.place_info())
        self.app.store.create("mail", "Hello", "Body", "!a1b2c3d4")
        page.refresh()
        self.root.update_idletasks()
        rows = page.listing.get_children()
        self.assertEqual(len(rows), 1)
        self.assertFalse(page.empty.place_info())
        self.assertIn("Draft", page.listing.item(rows[0], "values")[0])
        page.listing.selection_set(rows[0])
        page.on_select()
        self.assertTrue(page.send_btn._enabled)
        self.assertEqual(page.detail_title.cget("text"), "Hello")

    def test_hidden_pages_do_not_poll(self):
        page = self.app.page_objects["locals"]
        self.app.navigate("home")
        with patch.object(self.app.node_directory, "search") as search:
            page.refresh()
        search.assert_not_called()

    def test_theme_change_keeps_log_server_and_page(self):
        supervisor = Mock(running=True)
        self.app.supervisor = supervisor
        self.app.log("keep me")
        self.app.navigate("settings")
        self.app.appearance.set("light")
        self.app.rebuild()
        self.root.update_idletasks()
        self.assertIs(self.app.supervisor, supervisor)
        self.assertIn("keep me", self.app.output.get("1.0", "end"))
        self.assertEqual(self.app.current_page, "settings")
        self.assertFalse(self.app.theme.is_dark)
        supervisor.stop.assert_not_called()

    def test_invalid_tcp_host_shows_inline_error(self):
        self.app.connection.set("tcp")
        self.app.address.set("http://radio")
        self.root.update_idletasks()
        self.assertIn("not a URL", self.app.address_field.error.cget("text"))
        self.app.address.set("meshtastic.local")
        self.assertEqual(self.app.address_field.error.cget("text"), "")

    def test_disabled_button_ignores_activation(self):
        clicked = Mock()
        button = ui.Button(self.root, self.app.theme, "Go", clicked)
        button.set_enabled(False)
        button._invoke()
        clicked.assert_not_called()
        button.set_enabled(True)
        button._invoke()
        clicked.assert_called_once()


if __name__ == "__main__":
    unittest.main()
