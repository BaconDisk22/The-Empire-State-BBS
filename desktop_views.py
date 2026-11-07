"""Messages, Bulletin and Locals pages for the Empire State BBS desktop app.

Pages are built once inside the main window and refreshed only while they
are visible. The message safety flow is unchanged: saving never transmits,
Send transmits one record once after confirmation, nothing retries
automatically, and "sent" never claims RF delivery.
"""
import math
import sqlite3
import time
import tkinter as tk
from tkinter import messagebox

import empire_ui as ui
from desktop_session import MAX_PAYLOAD

SPACE = ui.SPACE

# Persisted post states -> (human label, tone). Unknown states fall back safely.
STATE_LABELS = {
    "draft": ("Draft", "neutral"),
    "queued": ("Queued", "info"),
    "sending": ("Sending…", "info"),
    "sent": ("Sent · unconfirmed", "info"),
    "acknowledged": ("Acknowledged", "success"),
    "failed": ("Failed", "danger"),
    "unknown": ("Delivery unknown", "warning"),
    "received": ("Received", "accent"),
}


def state_label(state):
    return STATE_LABELS.get(state, (str(state or "Unknown").capitalize(), "neutral"))


def observation_age(seen, now):
    """Describe receipt age, never inferred reachability."""
    if (not isinstance(seen, (int, float)) or isinstance(seen, bool)
            or not math.isfinite(seen) or seen <= 0 or seen > now):
        return 'Unknown'
    seconds = now - seen
    if seconds < 900:
        return 'Recent observation'
    return 'Stale observation'


def relative_time(stamp, now=None):
    """'just now', '5 min ago', '3 h ago', or a date for older records."""
    now = time.time() if now is None else now
    if (not isinstance(stamp, (int, float)) or isinstance(stamp, bool)
            or not math.isfinite(stamp) or stamp <= 0 or stamp > now + 60):
        return "Unknown"
    delta = max(0, now - stamp)
    if delta < 45:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60) or 1} min ago"
    if delta < 86400:
        return f"{int(delta // 3600)} h ago"
    return time.strftime("%b %d, %H:%M", time.localtime(stamp))


def radio_bytes(kind, subject, body, is_reply=False):
    """UTF-8 size of the text DesktopStore.payload() would transmit."""
    prefix = 'Bulletin: ' if kind == 'bulletin' else ''
    if is_reply:
        prefix += 'Reply: '
    return len((prefix + subject.strip() + '\n' + body.strip()).encode('utf-8'))


def page_header(parent, theme, title, subtitle, nyc_name=None):
    head = ui.frame(parent, theme)
    words = ui.frame(head, theme)
    words.pack(side="left", fill="x", expand=True)
    if nyc_name:
        ui.text(words, theme, nyc_name.upper(), "overline", "accent").pack(anchor="w")
    ui.text(words, theme, title, "title").pack(anchor="w")
    ui.wrap_to_width(ui.text(words, theme, subtitle, "body", "text_muted")).pack(
        anchor="w", fill="x", pady=(SPACE["xxs"], 0))
    actions = ui.frame(head, theme)
    actions.pack(side="right", anchor="s")
    return head, actions


class PostsPage:
    """The Grapevine (mail) and The Bulletin (local board)."""

    def __init__(self, app, parent, kind):
        self.app, self.kind = app, kind
        self.theme = theme = app.theme
        self.entries = {}
        self.rendered_detail = ()  # sentinel: forces the first render
        self.job = None
        mail = kind == 'mail'
        self.frame = ui.frame(parent, theme)
        head, actions = page_header(
            self.frame, theme, "Messages" if mail else "Bulletin board",
            ("Direct messages received by your BBS radio, plus drafts written on this Mac."
             if mail else "Local General-board posts and replies created on this Mac."),
            "The Grapevine" if mail else "The Bulletin")
        head.pack(fill="x", padx=SPACE["xl"], pady=(SPACE["xl"], SPACE["md"]))

        self.more_btn = ui.Button(actions, theme, "More", self.open_more, "ghost", "more", bg="bg",
                                  tooltip="Retry a failed send, open legacy drafts or browse the BBS database")
        self.more_btn.pack(side="right", padx=(SPACE["xs"], 0))
        self.send_btn = ui.Button(actions, theme, "Send…", self.send, "secondary", "send", bg="bg",
                                  tooltip="Transmit the selected draft once over the radio")
        self.send_btn.pack(side="right", padx=(SPACE["xs"], 0))
        self.reply_btn = ui.Button(actions, theme, "Reply", lambda: self.compose(True),
                                   "secondary", "reply", bg="bg")
        self.reply_btn.pack(side="right", padx=(SPACE["xs"], 0))
        self.new_btn = ui.Button(actions, theme, "New message" if mail else "New post",
                                 self.compose, "primary", "new", bg="bg")
        self.new_btn.pack(side="right", padx=(SPACE["xs"], 0))

        how = ui.Collapsible(self.frame, theme, "How saving and sending work", bg="bg")
        how.pack(fill="x", padx=SPACE["xl"])
        for line in (
            "Save keeps a draft on this Mac only. Nothing is transmitted.",
            "Send… transmits one draft to one node, once, after you confirm.",
            "“Sent · unconfirmed” means your local radio accepted it — over-the-air delivery is not verified.",
            "Nothing is retried automatically. A failed send can be copied to a new draft from More.",
        ):
            ui.wrap_to_width(ui.text(how.body, theme, "•  " + line, "caption", "text_muted")).pack(
                anchor="w", fill="x", pady=1)

        body = ui.frame(self.frame, theme)
        body.pack(fill="both", expand=True, padx=SPACE["xl"], pady=(SPACE["md"], SPACE["xl"]))
        self.body = body
        self.banner = ui.Banner(self.frame, theme)
        self.banner.place_with(fill="x", padx=SPACE["xl"], pady=(SPACE["sm"], 0), before=body)
        body.rowconfigure(0, weight=3)
        body.rowconfigure(1, weight=2)
        body.columnconfigure(0, weight=1)
        self.table_box = ui.frame(body, theme)
        self.table_box.grid(row=0, column=0, sticky="nsew")
        box, self.listing = ui.treeview(self.table_box, theme, [
            ('state', 'Status', 160, False),
            ('recipient', 'To / from', 150, False),
            ('subject', 'Subject', 420, True),
            ('when', 'When', 120, False),
        ])
        box.pack(fill="both", expand=True)
        self.empty = ui.EmptyState(
            self.table_box, theme, "messages" if mail else "bulletin",
            "No messages yet" if mail else "No bulletin posts yet",
            ("Messages sent to your BBS node appear here while the server runs. "
             "You can also write a draft now — it stays on this Mac until you send it."
             if mail else "Posts you write here are saved to the local General board. "
             "They are never broadcast automatically."),
            ("New message" if mail else "New post", self.compose, "new"), bg="surface")

        detail = ui.Card(body, theme, padding="lg")
        detail.grid(row=1, column=0, sticky="nsew", pady=(SPACE["md"], 0))
        self.detail_title = ui.text(detail.body, theme, "", "headline", bg="surface")
        self.detail_title.pack(anchor="w", fill="x")
        self.detail_meta = ui.text(detail.body, theme, "", "caption", "text_muted", "surface")
        self.detail_meta.pack(anchor="w", fill="x", pady=(SPACE["xxs"], SPACE["sm"]))
        _border, self.detail = ui.text_area(detail.body, theme, height=5, bg_slot="surface_sunken")
        _border.pack(fill="both", expand=True)
        self.detail.configure(state="disabled")

        self.listing.bind('<<TreeviewSelect>>', lambda _e: self.on_select())
        self.listing.bind('<Double-1>', lambda _e: self.send() if self.can_send() else None)
        self.on_select()

    # ------------------------------------------------------------ helpers
    def notify(self, message, tone="info"):
        self.banner.show(message, tone)

    def selected(self):
        values = self.listing.selection()
        return self.entries.get(values[0]) if values else None

    def can_send(self):
        record = self.selected()
        return bool(record and record.get('state') == 'draft')

    def on_select(self):
        record = self.selected()
        self.send_btn.set_enabled(self.can_send())
        if self.kind == 'mail':
            self.reply_btn.set_enabled(bool(record and record.get('state') == 'received'))
        else:
            self.reply_btn.set_enabled(bool(record and record.get('kind') == 'bulletin'))
        self.render_detail(record)

    def render_detail(self, record):
        # Only redraw when the content changes: avoids flicker and keeps the
        # reader's scroll position and text selection during live refresh.
        signature = None if record is None else tuple(sorted(
            (k, str(v)) for k, v in record.items()))
        if signature == self.rendered_detail:
            return
        self.rendered_detail = signature
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if record is None:
            self.detail_title.configure(text="Nothing selected")
            self.detail_meta.configure(text="Choose a row above to read it here.")
        else:
            label, _tone = state_label(record.get('state'))
            self.detail_title.configure(text=record.get('subject') or "(no subject)")
            who = record.get('recipient') or "Local only"
            direction = "From" if record.get('state') == 'received' else "To"
            meta = f"{label}  ·  {direction} {who}"
            stamp = record.get('created', record.get('seen'))
            if stamp:
                meta += "  ·  " + relative_time(stamp)
            self.detail_meta.configure(text=meta)
            self.detail.insert("end", record.get('body', ''))
            note = record.get('detail') or ('Received packet; not proof of a direct neighbor'
                                            if record.get('state') == 'received' else '')
            if note:
                self.detail.insert("end", "\n\n" + note)
            if record.get('parent'):
                self.detail.insert("end", "\nReply to local post " + record['parent'])
        self.detail.configure(state="disabled")

    # ------------------------------------------------------------ refresh
    def activate(self):
        self.refresh()

    def refresh(self):
        if self.job:
            try:
                self.frame.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if not self.frame.winfo_exists():
            return
        if getattr(self.app, "current_page", None) not in (None, self.page_key()):
            return  # hidden pages do not poll the database
        try:
            records = [r for r in self.app.store.records('posts') if r['kind'] == self.kind]
            if self.kind == 'mail':
                records += [dict(r, id='rx-' + r['key'], state='received', recipient=r['sender'],
                                 subject=(r['body'] or '')[:90])
                            for r in self.app.store.records('received')]
                records.sort(key=lambda r: r.get('created', r.get('seen')) or 0, reverse=True)
            current = {r['id']: r for r in records}
            for item in list(self.entries):
                if item not in current and self.listing.exists(item):
                    self.listing.delete(item)
            for index, (key, record) in enumerate(current.items()):
                label, tone = state_label(record['state'])
                values = (ui.ICON[ui.TONES[tone][2]] + "  " + label,
                          record['recipient'] or 'Local only', record['subject'],
                          relative_time(record.get('created', record.get('seen'))))
                tags = ("even" if index % 2 else "odd",)
                if self.listing.exists(key):
                    if self.listing.item(key, 'values') != values:
                        self.listing.item(key, values=values, tags=tags)
                    if self.listing.index(key) != index:
                        self.listing.move(key, '', index)
                else:
                    self.listing.insert('', index, iid=key, values=values, tags=tags)
            self.entries.clear()
            self.entries.update(current)
            if records:
                self.empty.place_forget()
            else:
                self.empty.place(in_=self.table_box, relx=0, rely=0, relwidth=1, relheight=1)
            if self.banner.tone == "danger" and self.banner.message().startswith("Unable to read"):
                self.banner.clear()
            self.on_select()
        except (OSError, sqlite3.Error, ValueError) as exc:
            self.notify('Unable to read local records: ' + str(exc), "danger")
        self.job = self.frame.after(1500, self.refresh)

    def page_key(self):
        return 'messages' if self.kind == 'mail' else 'bulletin'

    # ------------------------------------------------------------ actions
    def open_more(self):
        theme = self.theme
        menu = tk.Menu(self.frame, tearoff=0, bg=theme["surface"], fg=theme["text"],
                       activebackground=theme["accent_soft"], activeforeground=theme["text"],
                       font=theme.font("body"))
        menu.add_command(label="Retry failed send as new draft…", command=self.retry)
        if self.kind == 'mail':
            menu.add_command(label="Legacy drafts…", command=self.app.list_local_mail_drafts)
        menu.add_separator()
        menu.add_command(label="Browse BBS database…", command=lambda: self.app.browse_local_records(
            'Local BBS ' + ('mail' if self.kind == 'mail' else 'bulletins'),
            'mail' if self.kind == 'mail' else 'bulletins',
            ('id', 'sender_short_name', 'subject', 'content')))
        x = self.more_btn.winfo_rootx()
        y = self.more_btn.winfo_rooty() + self.more_btn.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def compose(self, reply=False):
        app, theme, kind = self.app, self.theme, self.kind
        parent = self.selected() if reply else None
        defaults = {}
        if reply and kind == 'mail':
            try:
                defaults = app.store.reply_fields(parent['key'] if parent and 'key' in parent else '')
            except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
                self.notify(str(exc), "warning")
                return
            parent = None
        elif reply and (not parent or parent.get('kind') != 'bulletin'):
            self.notify('Select a Bulletin post to reply to.', "warning")
            return
        if reply:
            title = 'Reply to message' if kind == 'mail' else 'Reply to post'
        else:
            title = 'New message' if kind == 'mail' else 'New bulletin post'
        editor = ui.sheet(app.root, theme, title + ' | The Empire State BBS', 640, 600)
        pad = ui.frame(editor, theme)
        pad.pack(fill="both", expand=True, padx=SPACE["xl"], pady=SPACE["xl"])
        ui.text(pad, theme, title, "title").pack(anchor="w")
        ui.wrap_to_width(ui.text(pad, theme, "Saved on this Mac only. Nothing is transmitted until you "
                                 "select the draft and choose Send…", "body", "text_muted")).pack(
            anchor="w", fill="x", pady=(SPACE["xxs"], SPACE["lg"]))
        fields = {}
        recipient = ui.Field(pad, theme, "Recipient node ID",
                             tk.StringVar(value=defaults.get('recipient', '')),
                             "A Meshtastic node ID like !a1b2c3d4. Needed to send; optional for a local save.",
                             bg="bg")
        recipient.pack(fill="x")
        subject_default = ('Re: ' + parent['subject']) if parent else defaults.get('subject', '')
        subject = ui.Field(pad, theme, "Subject", tk.StringVar(value=subject_default), bg="bg")
        subject.pack(fill="x", pady=(SPACE["md"], 0))
        fields['recipient'], fields['subject'] = recipient, subject
        ui.text(pad, theme, "Message", "label").pack(anchor="w", pady=(SPACE["md"], SPACE["xs"]))
        border, body = ui.text_area(pad, theme, height=8)
        border.pack(fill="both", expand=True)
        counter = ui.text(pad, theme, "", "caption", "text_muted")
        counter.pack(anchor="e", pady=(SPACE["xs"], 0))

        def update_counter(*_args):
            if not body.winfo_exists():
                return
            size = radio_bytes(kind, subject.value(), body.get('1.0', 'end-1c'), bool(parent))
            if size > MAX_PAYLOAD:
                counter.configure(text=f"{size} / {MAX_PAYLOAD} bytes — too long to send over radio "
                                       "(you can still save it locally)", fg=theme["warning"])
            else:
                counter.configure(text=f"{size} / {MAX_PAYLOAD} bytes for radio", fg=theme["text_muted"])
        subject.variable.trace_add("write", update_counter)
        body.bind("<<Modified>>", lambda _e: (body.edit_modified(False), update_counter()))
        update_counter()

        def save(_event=None):
            try:
                app.store.create(kind, subject.value(), body.get('1.0', 'end-1c'),
                                 recipient.value(), parent['id'] if parent else None)
            except (ValueError, OSError, sqlite3.Error) as exc:
                error.show(str(exc), "danger")
                return "break"
            editor.destroy()
            self.notify('Draft saved on this Mac. Select it and choose Send… to transmit once.', "success")
            app.toast("Draft saved — nothing was transmitted")
            self.refresh()
            return "break"

        buttons = ui.frame(pad, theme)
        buttons.pack(fill="x", pady=(SPACE["lg"], 0))
        error = ui.Banner(pad, theme)
        error.place_with(fill="x", pady=(SPACE["sm"], 0), before=buttons)
        ui.Button(buttons, theme, "Save draft", save, "primary", "check", bg="bg").pack(side="right")
        ui.Button(buttons, theme, "Cancel", editor.destroy, "ghost", bg="bg").pack(
            side="right", padx=(0, SPACE["sm"]))
        ui.text(buttons, theme, "⌘S to save · Esc to cancel", "caption", "text_faint").pack(side="left")
        editor.bind("<Command-s>", save)
        editor.bind("<Control-s>", save)
        (recipient.entry if not recipient.value() else
         (subject.entry if not subject.value() else body)).focus_set()

    def send(self):
        app = self.app
        record = self.selected()
        if not record or record.get('state') != 'draft':
            self.notify('Select a saved draft to send. Records that were already attempted cannot be resent.',
                        "warning")
            return
        monitor = app.supervisor
        if app.demo.get() or not monitor or not monitor.running or not monitor.ready:
            self.notify('Sending needs a running BBS server (not Demo mode). Start it from Connection, '
                        'wait for “Ready”, then try again.', "warning")
            return
        try:
            payload = app.store.payload(record)
            if not messagebox.askyesno(
                    'Send this message once?',
                    f"To {record['recipient']}\n\n{payload}\n\n"
                    "It will be transmitted once. There is no automatic resend, and "
                    "over-the-air delivery is not guaranteed.", parent=app.root):
                return
            app.store.queue(record['id'])
            try:
                monitor.send_desktop(record['id'])
            except (OSError, ValueError) as exc:
                # A partial pipe write is ambiguous; preserve the claim for inspection.
                self.notify('The send request may not have reached the server, and it will not be '
                            'retried: ' + str(exc), "danger")
                return
            self.notify('Send requested. The Status column updates as the radio reports back. '
                        'No automatic retry.', "info")
            self.refresh()
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.notify(str(exc), "danger")

    def retry(self):
        record = self.selected()
        if not record or record.get('state') != 'failed':
            self.notify('Select a Failed send first. Records with unknown delivery cannot be retried.',
                        "warning")
            return
        if not messagebox.askyesno(
                'Create a retry draft?',
                'This copies the failed message into a new local draft and keeps the failed record. '
                'Sending it later needs another confirmation.\n\n'
                'If the original was actually received despite the error, the recipient may get it twice.',
                parent=self.app.root):
            return
        try:
            self.app.store.retry_draft(record['id'])
            self.notify('Retry draft saved on this Mac. Select it and choose Send… to transmit once.',
                        "success")
            self.refresh()
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.notify(str(exc), "danger")


class NodesPage:
    """The Locals: nodes observed by the radio. Passive; never transmits."""

    def __init__(self, app, parent):
        self.app = app
        self.theme = theme = app.theme
        self.job = None
        self.nodes = []
        self.frame = ui.frame(parent, theme)
        head, actions = page_header(
            self.frame, theme, "Locals",
            "Nodes your radio has heard. This list is passive — nothing is transmitted to discover nodes.",
            "The Locals")
        head.pack(fill="x", padx=SPACE["xl"], pady=(SPACE["xl"], SPACE["md"]))
        self.search = tk.StringVar()
        search = ui.Field(actions, theme, "Filter", self.search, bg="bg", width=24)
        search.pack(side="right")
        self.search_entry = search.entry
        self.search.trace_add("write", lambda *_a: self.render())

        stats = ui.frame(self.frame, theme)
        stats.pack(fill="x", padx=SPACE["xl"])
        self.stat_total = ui.StatusPill(stats, theme, "0 nodes", "neutral", bg="bg")
        self.stat_total.pack(side="left", padx=(0, SPACE["lg"]))
        self.stat_recent = ui.StatusPill(stats, theme, "0 recent", "success", bg="bg")
        self.stat_recent.pack(side="left", padx=(0, SPACE["lg"]))
        self.stat_stale = ui.StatusPill(stats, theme, "0 stale", "warning", bg="bg")
        self.stat_stale.pack(side="left")

        info = ui.Collapsible(self.frame, theme, "What these values mean", bg="bg")
        info.pack(fill="x", padx=SPACE["xl"], pady=(SPACE["sm"], 0))
        for line in (
            "Last heard is when this Mac received a packet from the node.",
            "Recent = heard in the last 15 minutes. Stale = 15 minutes or longer.",
            "SNR and RSSI describe the last received packet, which may have been relayed.",
            "None of these prove a direct link, distance, or that a node is online now. Records persist across sessions.",
        ):
            ui.wrap_to_width(ui.text(info.body, theme, "•  " + line, "caption", "text_muted")).pack(
                anchor="w", fill="x", pady=1)

        self.table_box = ui.frame(self.frame, theme)
        self.table_box.pack(fill="both", expand=True, padx=SPACE["xl"], pady=(SPACE["md"], SPACE["xl"]))
        self.banner = ui.Banner(self.frame, theme)
        self.banner.place_with(fill="x", padx=SPACE["xl"], pady=(SPACE["sm"], 0), before=self.table_box)
        box, self.listing = ui.treeview(self.table_box, theme, [
            ('id', 'Node ID', 120, False), ('name', 'Name', 200, True),
            ('seen', 'Last heard', 150, False), ('age', 'Status', 120, False),
            ('snr', 'SNR (dB)', 90, False), ('rssi', 'RSSI (dBm)', 100, False),
        ])
        box.pack(fill="both", expand=True)
        self.empty = ui.EmptyState(
            self.table_box, theme, "locals", "No nodes heard yet",
            "Start the BBS with your radio connected. Nodes appear here as their packets are received.",
            ("Open Connection", app.show_radio, "connection"), bg="surface")

    def activate(self):
        self.refresh()

    def refresh(self):
        if self.job:
            try:
                self.frame.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if not self.frame.winfo_exists():
            return
        if getattr(self.app, "current_page", None) not in (None, 'locals'):
            return
        try:
            self.nodes = self.app.store.records('nodes')
            self.banner.clear()
        except (OSError, sqlite3.Error) as exc:
            self.banner.show('Unable to read observed nodes: ' + str(exc), "danger")
        self.render()
        self.job = self.frame.after(2000, self.refresh)

    def render(self):
        now = time.time()
        needle = self.search.get().strip().casefold()
        recent = stale = 0
        rows = []
        for node in self.nodes:
            age = observation_age(node['seen'], now)
            recent += age == 'Recent observation'
            stale += age == 'Stale observation'
            name = node['name'] or 'Unknown'
            if needle and needle not in str(node['id']).casefold() and needle not in name.casefold():
                continue
            tone = {'Recent observation': 'success', 'Stale observation': 'warning'}.get(age, 'neutral')
            status = {'Recent observation': 'Recent', 'Stale observation': 'Stale'}.get(age, 'Unknown')
            seen = (relative_time(node['seen'], now) if age != 'Unknown' else 'Unknown')
            rows.append((str(node['id']), (
                node['id'], name, seen, ui.ICON[ui.TONES[tone][2]] + "  " + status,
                node['snr'] if node['snr'] is not None else '—',
                node['rssi'] if node['rssi'] is not None else '—')))
        # Update rows in place to preserve selection and scroll position.
        current = set(self.listing.get_children())
        wanted = set()
        for index, (node_id, values) in enumerate(rows):
            wanted.add(node_id)
            tags = ("even" if index % 2 else "odd",)
            if node_id in current:
                if tuple(str(v) for v in self.listing.item(node_id, 'values')) != tuple(str(v) for v in values):
                    self.listing.item(node_id, values=values, tags=tags)
                if self.listing.index(node_id) != index:
                    self.listing.move(node_id, '', index)
            else:
                self.listing.insert('', index, iid=node_id, values=values, tags=tags)
        for missing in current - wanted:
            self.listing.delete(missing)
        total = len(self.nodes)
        self.stat_total.set(f"{total} node{'s' if total != 1 else ''} heard", "neutral")
        self.stat_recent.set(f"{recent} recent", "success" if recent else "neutral")
        self.stat_stale.set(f"{stale} stale", "warning" if stale else "neutral")
        if rows:
            self.empty.place_forget()
        elif self.nodes:
            self.empty.place_forget()
            self.banner.show(f'No nodes match “{self.search.get().strip()}”.', "info")
        else:
            self.empty.place(in_=self.table_box, relx=0, rely=0, relwidth=1, relheight=1)


def open_posts(app, kind):
    """Compatibility entry point: navigate to the Messages or Bulletin page."""
    app.navigate('messages' if kind == 'mail' else 'bulletin')


def open_nodes(app):
    """Compatibility entry point: navigate to the Locals page."""
    app.navigate('locals')
