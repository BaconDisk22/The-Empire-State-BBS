"""Tk views for local records, explicit transmissions, and observed packets."""
import sqlite3
import time
import tkinter as tk
from tkinter import messagebox, ttk

from desktop_session import MAX_PAYLOAD


def window(app, title):
    win = tk.Toplevel(app.root)
    win.title(title + ' | The Empire State BBS')
    win.geometry('920x650')
    return win


def open_posts(app, kind):
    win = window(app, 'The Grapevine' if kind == 'mail' else 'The Bulletin')
    tk.Label(win, text=('Live received text and local mail' if kind == 'mail' else 'General board • local Bulletin posts and replies'),
             font=('Helvetica', 18, 'bold')).pack(pady=10)
    tk.Label(win, text='Save stays on this computer. Send explicitly submits one text to one node.\n'
             'Sent = local radio API returned; RF delivery is unverified. No automatic retry or BBS sync.',
             wraplength=860).pack()
    listing = ttk.Treeview(win, columns=('state', 'recipient', 'subject'), show='headings', height=12)
    for col, label in [('state', 'State / source'), ('recipient', 'To / from node'), ('subject', 'Subject / text')]:
        listing.heading(col, text=label)
    listing.pack(fill='both', expand=True, padx=12, pady=10)
    detail = tk.Text(win, height=7, wrap='word', state='disabled')
    detail.pack(fill='x', padx=12)
    notice = tk.StringVar()
    tk.Label(win, textvariable=notice, wraplength=850).pack()
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
        if reply and (not parent or parent.get('kind') != 'bulletin'):
            notice.set('Select a local Bulletin post to reply to.')
            return
        editor = window(app, 'Reply to Bulletin' if reply else 'New local ' + kind)
        fields = {}
        for key, label in [('recipient', 'Recipient node ID (optional for local saves)'), ('subject', 'Subject')]:
            tk.Label(editor, text=label).pack(anchor='w', padx=15, pady=(12, 0))
            var = tk.StringVar(value=('Re: ' + parent['subject']) if parent and key == 'subject' else '')
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

    actions = tk.Frame(win)
    actions.pack(pady=10)
    tk.Button(actions, text='NEW LOCAL POST' if kind == 'bulletin' else 'NEW LOCAL MESSAGE', command=compose).pack(side='left', padx=5)
    if kind == 'bulletin':
        tk.Button(actions, text='REPLY LOCALLY', command=lambda: compose(True)).pack(side='left', padx=5)
    tk.Button(actions, text='SEND SELECTED ONCE…', command=send).pack(side='left', padx=5)
    if kind == 'mail':
        tk.Button(actions, text='LEGACY DRAFTS', command=app.list_local_mail_drafts).pack(side='left', padx=5)
    tk.Button(actions, text='BBS DATABASE', command=lambda: app.browse_local_records(
        'Local BBS ' + kind, 'mail' if kind == 'mail' else 'bulletins',
        ('id', 'sender_short_name', 'subject', 'content'))).pack(side='left', padx=5)
    listing.bind('<<TreeviewSelect>>', show_detail)
    refresh()


def open_nodes(app):
    win = window(app, 'The Locals')
    tk.Label(win, text='Observed packets • last seen is local receipt time\n'
             'Signal values describe the last received packet, which may be relayed.\n'
             'They do not prove a direct link, distance, or current online status. Records persist across sessions.').pack(pady=15)
    columns = ('id', 'name', 'seen', 'snr', 'rssi')
    listing = ttk.Treeview(win, columns=columns, show='headings')
    for key, label in zip(columns, ('Node ID', 'Observed name', 'Last seen', 'Packet SNR (dB)', 'Packet RSSI (dBm)')):
        listing.heading(key, text=label)
        listing.column(key, width=160)
    listing.pack(fill='both', expand=True, padx=10, pady=10)
    notice = tk.StringVar()
    tk.Label(win, textvariable=notice).pack()
    def refresh():
        if not win.winfo_exists():
            return
        try:
            nodes = app.store.records('nodes')
            children = listing.get_children()
            if children:
                listing.delete(*children)
            for node in nodes:
                listing.insert('', 'end', values=(node['id'], node['name'] or 'Unknown',
                    time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(node['seen'])),
                    node['snr'] if node['snr'] is not None else 'Unavailable',
                    node['rssi'] if node['rssi'] is not None else 'Unavailable'))
            notice.set(f'{len(nodes)} observed node(s); no discovery transmissions')
        except (OSError, sqlite3.Error) as exc:
            notice.set('Unable to read observed nodes: ' + str(exc))
        win.after(2000, refresh)
    refresh()
