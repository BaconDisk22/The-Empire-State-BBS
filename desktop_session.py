"""Durable desktop records and explicit, one-shot sends through the BBS radio.

No reconnect/startup path sends queued records. 'sent' means the local radio
API returned, never proof of RF delivery. SQLite claims survive process death.
"""
from contextlib import contextmanager
import json
import math
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

NODE = re.compile(r"![0-9a-fA-F]{8}")
MAX_PAYLOAD = 200  # conservative UTF-8 budget; never silently split a message


class DesktopStore:
    def __init__(self, path, bbs_path=None):
        self.path = str(path)
        self.bbs_path = str(bbs_path or Path(path).parent / "bulletins.db")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS bbs.bulletins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, board TEXT NOT NULL,
                    sender_short_name TEXT NOT NULL, date TEXT NOT NULL,
                    subject TEXT NOT NULL, content TEXT NOT NULL, unique_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, recipient TEXT,
                    subject TEXT NOT NULL, body TEXT NOT NULL, parent TEXT,
                    state TEXT NOT NULL, created REAL NOT NULL, detail TEXT,
                    packet_id TEXT);
                CREATE TABLE IF NOT EXISTS received (
                    key TEXT PRIMARY KEY, sender TEXT, body TEXT, seen REAL);
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY, name TEXT, seen REAL,
                    snr REAL, rssi REAL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("ATTACH DATABASE ? AS bbs", (self.bbs_path,))
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, kind, subject, body, recipient='', parent=None):
        if kind not in ('mail', 'bulletin'):
            raise ValueError('Invalid post type')
        if not all(isinstance(x, str) for x in (subject, body, recipient)):
            raise ValueError('Fields must be text')
        subject, body, recipient = subject.strip(), body.strip(), recipient.strip().lower()
        if not subject or not body or len(subject) > 120 or len(body) > 4000:
            raise ValueError('Subject and body required (120 / 4000 characters maximum)')
        if '\n' in subject or '\r' in subject or '\t' in subject:
            raise ValueError('Subject must fit on one line')
        if any(ord(c) < 32 and c not in '\n\t' for c in subject + body):
            raise ValueError('Control characters are not allowed')
        if recipient and (not NODE.fullmatch(recipient) or recipient in ('!ffffffff', '!00000000')):
            raise ValueError('Use an individual node ID such as !1234abcd; broadcast is not allowed')
        post_id = uuid.uuid4().hex
        with self.connect() as db:
            if parent and (kind != 'bulletin' or not db.execute("SELECT 1 FROM posts WHERE id=? AND kind='bulletin'", (parent,)).fetchone()):
                raise ValueError('Reply parent must be an existing local bulletin')
            db.execute('INSERT INTO posts VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (post_id, kind, recipient, subject, body, parent, 'draft', time.time(), 'Saved locally; not transmitted', None))
            if kind == "bulletin":
                # Direct local insertion deliberately avoids automatic sync and urgent broadcasts.
                db.execute("INSERT INTO bbs.bulletins (board,sender_short_name,date,subject,content,unique_id) VALUES (?,?,?,?,?,?)",
                           ("General", "Desktop", time.strftime("%Y-%m-%d %H:%M"), subject, body, post_id))
        return post_id

    def records(self, table):
        if table not in ('posts', 'received', 'nodes'):
            raise ValueError('Invalid table')
        column = 'created' if table == 'posts' else 'seen'
        with self.connect() as db:
            return [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY {column} DESC')]

    def get(self, post_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM posts WHERE id=?', (post_id,)).fetchone()
            if not row:
                raise ValueError('Unknown local record')
            return dict(row)

    def payload(self, record):
        if not NODE.fullmatch(record['recipient'] or '') or record['recipient'] in ('!ffffffff', '!00000000'):
            raise ValueError('An individual recipient node ID is required to transmit')
        prefix = 'Bulletin: ' if record['kind'] == 'bulletin' else ''
        if record['parent']:
            prefix += 'Reply: '
        text = prefix + record['subject'] + '\n' + record['body']
        if len(text.encode('utf-8')) > MAX_PAYLOAD:
            raise ValueError(f'Transmission exceeds {MAX_PAYLOAD} UTF-8 bytes; shorten it. Local posts may be longer.')
        return text

    def queue(self, post_id):
        self.payload(self.get(post_id))
        self.change(post_id, 'draft', 'queued', 'Explicit send requested; no automatic retry')

    def change(self, post_id, old, new, detail, packet_id=None):
        with self.connect() as db:
            result = db.execute('UPDATE posts SET state=?, detail=?, packet_id=? WHERE id=? AND state=?',
                                (new, detail, packet_id, post_id, old))
            if result.rowcount != 1:
                raise ValueError('Already attempted or state changed; no resend')


class RadioSession:
    def __init__(self, interface, store, available=lambda: True):
        self.interface, self.store, self.available = interface, store, available
        self.lock = threading.Lock()
        with store.connect() as db:
            db.execute("UPDATE posts SET state='unknown', detail='Server stopped during send; do not resend automatically' WHERE state='sending'")

    def send(self, post_id):
        with self.lock:
            record = self.store.get(post_id)
            payload = self.store.payload(record)
            if not self.available():
                self.store.change(post_id, 'queued', 'failed', 'Radio unavailable; nothing submitted')
                return
            # Commit the durable claim BEFORE touching the radio. Competing calls lose.
            self.store.change(post_id, 'queued', 'sending', 'Submitting to the existing server radio session')
            try:
                packet = self.interface.sendText(payload, destinationId=record['recipient'], wantAck=True)
                packet_id = getattr(packet, 'id', None)
            except Exception:
                self.store.change(post_id, 'sending', 'unknown', 'Radio call failed; delivery unknown. No automatic resend.')
                return
            self.store.change(post_id, 'sending', 'sent', 'Submitted to local radio; RF delivery unverified',
                              str(packet_id) if packet_id is not None else None)

    def observe(self, packet):
        sender = packet.get('fromId')
        if not isinstance(sender, str) or not NODE.fullmatch(sender):
            number = packet.get('from')
            if not isinstance(number, int) or not 0 < number < 0xffffffff:
                return
            sender = f'!{number:08x}'
        sender = sender.lower()
        if sender in ('!00000000', '!ffffffff'):
            return
        decoded = packet.get('decoded') or {}
        if not isinstance(decoded, dict):
            return
        user = decoded.get('user') or {}
        name = str(user.get('longName') or user.get('shortName') or '')[:100] if isinstance(user, dict) else ''
        def metric(key):
            value = packet.get(key)
            return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None
        now = time.time()
        with self.store.connect() as db:
            db.execute('''INSERT INTO nodes VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                          name=CASE WHEN excluded.name='' THEN nodes.name ELSE excluded.name END,
                          seen=excluded.seen, snr=excluded.snr, rssi=excluded.rssi''',
                       (sender, name, now, metric('rxSnr'), metric('rxRssi')))
            body = decoded.get('text')
            if isinstance(body, str):
                packet_id = packet.get('id')
                # Missing IDs cannot safely be deduplicated by text: repeated text may be intentional.
                key = f'{sender}:{packet_id}' if packet_id else uuid.uuid4().hex
                db.execute('INSERT OR IGNORE INTO received VALUES (?,?,?,?)', (key, sender, body, now))

    def read_commands(self, stream, stopping):
        if stream is None:
            return
        while not stopping.is_set():
            line = stream.readline(1025)
            if not line:
                return
            if len(line) > 1024 or not line.endswith('\n'):
                while line and not line.endswith('\n'):
                    line = stream.readline(1025)
                continue
            try:
                command = json.loads(line)
                if not isinstance(command, dict) or set(command) != {'send'}:
                    raise ValueError('Invalid command')
                if not isinstance(command['send'], str) or not re.fullmatch('[0-9a-f]{32}', command['send']):
                    raise ValueError('Invalid record ID')
                if not stopping.is_set():
                    self.send(command['send'])
            except (ValueError, TypeError, sqlite3.Error):
                # Fail closed; the durable record remains visible to the operator.
                continue
