"""Tk views for local records, explicit transmissions, and observed packets."""
import sqlite3
import math
import time
import tkinter as tk
from tkinter import messagebox, ttk

from desktop_session import MAX_PAYLOAD

# Match the NYC command-center shell while keeping the message safety flow intact.
INK = "#090B10"
PANEL = "#171A22"
ORANGE = "#FF791F"
PAPER = "#F5F1E9"
GREEN = "#44DF79"



def observation_age(seen, now):
    """Describe receipt age, never inferred reachability."""
    if (not isinstance(seen, (int, float)) or isinstance(seen, bool)
            or not math.isfinite(seen) or seen <= 0 or seen > now):
        return 'Unknown'
    seconds = now - seen
    if seconds < 900:
        return 'Recent observation'
    return 'Stale observation'


def window(app, title):
    win = tk.Toplevel(app.root)
    win.title(title + ' | The Empire State BBS')
    win.geometry('1060x720')
    win.minsize(850, 600)
    win.configure(bg=INK)
    # Keep only one live window per section. Reopening brings it to the front.
    return win


def open_posts(app, kind):
    key = 'grapevine' if kind == 'mail' else 'bulletin'
    existing = getattr(app, '_empire_views', {}).get(key)
    if existing is not None and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        existing.focus_force()
        return
    win = window(app, 'The Grapevine' if kind == 'mail' else 'The Bulletin')
    if not hasattr(app, '_empire_views'):
        app._empire_views = {}
    app._empire_views[key] = win
    tk.Label(win, text='THE GRAPEVINE  /  INBOX + DRAFTS' if kind == 'mail' else 'THE BULLETIN  /  LOCAL BOARD',
             bg=INK, fg=ORANGE, font=('Helvetica', 22, 'bold')).pack(anchor='w', padx=20, pady=(22, 5))
    tk.Label(win, text='LIVE RECEIVED TEXT + LOCAL MAIL' if kind == 'mail' else 'GENERAL BOARD • LOCAL POSTS + REPLIES',
             bg=INK, fg=PAPER, font=('Menlo', 10, 'bold')).pack(anchor='w', padx=20, pady=(0, 12))
    tk.Label(win, text='Save stays on this computer. Send explicitly submits one text to one node.\n'
             'Sent = local radio API returned; RF delivery is unverified. No automatic retry or BBS sync.',
             wraplength=960, bg=INK, fg=PAPER, justify='left').pack(anchor='w', padx=20)
    style = ttk.Style(win)
    style.configure('Empire.Treeview', background=PANEL, foreground=PAPER,
                    fieldbackground=PANEL, rowheight=32, font=('Helvetica', 11))
    style.configure('Empire.Treeview.Heading', background=INK, foreground=ORANGE,
                    font=('Helvetica', 11, 'bold'))
    style.map('Empire.Treeview', background=[('selected', '#854012')],
              foreground=[('selected', PAPER)])
    listing = ttk.Treeview(win, columns=('state', 'recipient', 'subject'),
                           show='headings', height=12, style='Empire.Treeview')
    for col, label in [('state', 'State / source'), ('recipient', 'To / from node'), ('subject', 'Subject / text')]:
        listing.heading(col, text=label)
    listing.pack(fill='both', expand=True, padx=12, pady=10)
    detail = tk.Text(win, height=7, wrap='word', state='disabled',
                     bg=PANEL, fg=PAPER, insertbackground=ORANGE, relief='flat',
                     padx=12, pady=10, font=('Menlo', 11))
    detail.pack(fill='x', padx=12)
    notice = tk.StringVar()
    tk.Label(win, textvariable=notice, wraplength=960, bg=INK,
             fg=GREEN, justify='left').pack(anchor='w', padx=20, pady=6)
    entries = {}

    def selected():
        values = listing.selection()
        return entries.get(values[0]) if values else None

    def show_detail(_event=None):
        record = selected()
        detail.configure(state='normal')
        detail.delete('1.0', 'end')
        if record:
            detail.insert('end', record.get('body', '') + '\n\n' + record.get('detail', 'Received packet; not proof of a direct neighbor'))
            if record.get('parent'):
                detail.insert('end', '\nReply to local post: ' + record['parent'])
        detail.configure(state='disabled')

    def refresh():
        if not win.winfo_exists():
            return
        try:
            records = [r for r in app.store.records('posts') if r['kind'] == kind]
            if kind == 'mail':
                records += [dict(r, id='rx-' + r['key'], state='received', recipient=r['sender'], subject=r['body'][:90])
                            for r in app.store.records('received')]
            current = {r['id']: r for r in records}
            for item in list(entries):
                if item not in current:
                    listing.delete(item)
            for key, record in current.items():
                values = (record['state'], record['recipient'] or 'Local only', record['subject'])
                if key in entries:
                    listing.item(key, values=values)
                else:
                    listing.insert('', 'end', iid=key, values=values)
            entries.clear()
            entries.update(current)
            show_detail()
        except (OSError, sqlite3.Error, ValueError) as exc:
            notice.set('Unable to read local records: ' + str(exc))
        win.after(1000, refresh)

    def compose(reply=False):
        parent = selected() if reply else None
        defaults = {}
        if reply and kind == 'mail':
            try:
                defaults = app.store.reply_fields(parent['key'] if parent else '')
            except (ValueError, KeyError, OSError, sqlite3.Error) as exc:
                notice.set(str(exc))
                return
            parent = None
        elif reply and (not parent or parent.get('kind') != 'bulletin'):
            notice.set('Select a local Bulletin post to reply to.')
            return
        editor = window(app, ('Reply to received message' if kind == 'mail' else 'Reply to Bulletin') if reply else 'New local ' + kind)
        fields = {}
        for key, label in [('recipient', 'Recipient node ID (optional for local saves)'), ('subject', 'Subject')]:
            tk.Label(editor, text=label).pack(anchor='w', padx=15, pady=(12, 0))
            var = tk.StringVar(value=('Re: ' + parent['subject']) if parent and key == 'subject' else defaults.get(key, ''))
            tk.Entry(editor, textvariable=var).pack(fill='x', padx=15)
            fields[key] = var
        tk.Label(editor, text=f'Body — radio messages limited to {MAX_PAYLOAD} UTF-8 bytes including subject').pack(pady=10)
        body = tk.Text(editor, height=12, wrap='word')
        body.pack(fill='both', expand=True, padx=15)
        error = tk.StringVar()
        tk.Label(editor, textvariable=error).pack()
        def save():
            try:
                app.store.create(kind, fields['subject'].get(), body.get('1.0', 'end-1c'),
                                 fields['recipient'].get(), parent['id'] if parent else None)
                notice.set('Saved locally. Select the record and Send once to transmit.')
                editor.destroy()
            except (ValueError, OSError, sqlite3.Error) as exc:
                error.set(str(exc))
        tk.Button(editor, text='SAVE LOCALLY — NO RADIO', command=save).pack(pady=15)

    def send():
        record = selected()
        if not record or record.get('state') != 'draft':
            notice.set('Select a saved local draft. Attempted records cannot be resent.')
            return
        monitor = app.supervisor
        if app.demo.get() or not monitor or not monitor.running or not monitor.ready:
            notice.set('Start a ready server session outside Demo mode before sending.')
            return
        try:
            payload = app.store.payload(record)
            if not messagebox.askyesno('Send once over the radio?',
                    f"To {record['recipient']}\n\n{payload}\n\nNo automatic resend. RF delivery is not guaranteed.", parent=win):
                return
            app.store.queue(record['id'])
            try:
                monitor.send_desktop(record['id'])
            except (OSError, ValueError) as exc:
                # A partial pipe write is ambiguous; preserve the claim for inspection.
                notice.set('Command submission uncertain; no retry: ' + str(exc))
                return
            notice.set('Send requested. Watch the persisted state below; no automatic retry.')
        except (ValueError, OSError, sqlite3.Error) as exc:
            notice.set(str(exc))

    actions = tk.Frame(win, bg=INK)
    actions.pack(pady=10)
    tk.Button(actions, text='NEW LOCAL POST' if kind == 'bulletin' else 'NEW LOCAL MESSAGE', command=compose).pack(side='left', padx=5)
    if kind == 'bulletin':
        tk.Button(actions, text='REPLY LOCALLY', command=lambda: compose(True)).pack(side='left', padx=5)
    tk.Button(actions, text='SEND SELECTED ONCE…', command=send).pack(side='left', padx=5)
    def retry():
        record = selected()
        if not record or record.get('state') != 'failed':
            notice.set('Select a failed attempt. Unknown delivery cannot be retried.')
            return
        if not messagebox.askyesno('Create a retry draft?',
                'This creates a local replacement draft and preserves the failed attempt. '
                'A later send requires another confirmation. A retry can duplicate a message if it was received despite the error.', parent=win):
            return
        try:
            app.store.retry_draft(record['id'])
            notice.set('Retry draft saved locally. Select it and Send once to transmit.')
        except (ValueError, OSError, sqlite3.Error) as exc:
            notice.set(str(exc))
    tk.Button(actions, text='RETRY FAILED AS DRAFT…', command=retry).pack(side='left', padx=5)
    if kind == 'mail':
        tk.Button(actions, text='REPLY TO RECEIVED…', command=lambda: compose(True)).pack(side='left', padx=5)
        tk.Button(actions, text='LEGACY DRAFTS', command=app.list_local_mail_drafts).pack(side='left', padx=5)
    tk.Button(actions, text='BBS DATABASE', command=lambda: app.browse_local_records(
        'Local BBS ' + kind, 'mail' if kind == 'mail' else 'bulletins',
        ('id', 'sender_short_name', 'subject', 'content'))).pack(side='left', padx=5)
    buttons = actions.winfo_children()
    for button in buttons:
        button.configure(bg=PANEL, fg=PAPER, activebackground=ORANGE,
                         activeforeground=INK, relief='flat', padx=12, pady=9,
                         font=('Helvetica', 10, 'bold'), cursor='hand2')
    for button in buttons:
        button.pack_forget()
    for index, button in enumerate(buttons):
        button.grid(row=index // 3, column=index % 3, padx=5, pady=3)
    listing.bind('<<TreeviewSelect>>', show_detail)
    refresh()


def open_nodes(app):
    existing = getattr(app, '_empire_views', {}).get('locals')
    if existing is not None and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        existing.focus_force()
        return
    win = window(app, 'The Locals')
    if not hasattr(app, '_empire_views'):
        app._empire_views = {}
    app._empire_views['locals'] = win
    tk.Label(win, text='THE LOCALS  /  OBSERVED NODES', bg=INK, fg=ORANGE,
             font=('Helvetica', 22, 'bold')).pack(anchor='w', padx=20, pady=(22, 5))
    tk.Label(win, text='Observed packets • last seen is local receipt time\n'
             'Signal values describe the last received packet, which may be relayed.\n'
             'Recent means received less than 15 minutes ago; stale means 15 minutes or more.\n'
             'They do not prove a direct link, distance, or current online status. Records persist across sessions.',
             bg=INK, fg=PAPER, justify='left').pack(anchor='w', padx=20, pady=12)
    columns = ('id', 'name', 'seen', 'age', 'snr', 'rssi')
    style = ttk.Style(win)
    style.configure('Empire.Treeview', background=PANEL, foreground=PAPER,
                    fieldbackground=PANEL, rowheight=32)
    style.configure('Empire.Treeview.Heading', background=INK, foreground=ORANGE)
    listing = ttk.Treeview(win, columns=columns, show='headings', style='Empire.Treeview')
    for key, label in zip(columns, ('Node ID', 'Observed name', 'Last seen', 'Observation age', 'Packet SNR (dB)', 'Packet RSSI (dBm)')):
        listing.heading(key, text=label)
        listing.column(key, width=140)
    listing.pack(fill='both', expand=True, padx=10, pady=10)
    notice = tk.StringVar()
    tk.Label(win, textvariable=notice, bg=INK, fg=GREEN).pack(anchor='w', padx=20, pady=8)
    def refresh():
        if not win.winfo_exists():
            return
        try:
            nodes = app.store.records('nodes')
            children = listing.get_children()
            if children:
                listing.delete(*children)
            for node in nodes:
                age = observation_age(node['seen'], time.time())
                listing.insert('', 'end', values=(node['id'], node['name'] or 'Unknown',
                    time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(node['seen'])) if age != 'Unknown' else 'Unknown',
                    age,
                    node['snr'] if node['snr'] is not None else 'Unavailable',
                    node['rssi'] if node['rssi'] is not None else 'Unavailable'))
            notice.set(f'{len(nodes)} observed node(s); no discovery transmissions')
        except (OSError, sqlite3.Error) as exc:
            notice.set('Unable to read observed nodes: ' + str(exc))
        win.after(2000, refresh)
    refresh()
