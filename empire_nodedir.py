"""The app's own node directory, beyond the radio's fixed-size node list.

A Meshtastic radio remembers a limited number of nodes (about 100 on an ESP32
without PSRAM) and forgets the least recently heard. The Empire State BBS keeps
every node it learns about in a private SQLite file beside its other data, so a
node the radio has dropped is still listed here with when it was last heard.

Two sources feed it, both passive (nothing is ever transmitted):
  * the radio's own node list (``interface.nodes``), merged on connect and
    every minute while the server runs;
  * packets this Mac actually receives, recorded as they arrive.

Only metadata is stored: id, names, hardware, role, signal, hops, battery and
position. Never message text. The BBS's mesh commands still use the radio's
own list; this directory is for the desktop app.

The server process writes and the desktop process reads, so every call opens
its own short-lived connection (WAL mode, busy timeout).
"""
import math
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

MAX_NODES = 20000
NODE_ID = re.compile(r"!?([0-9a-fA-F]{8})")
SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    short TEXT NOT NULL DEFAULT '',
    long TEXT NOT NULL DEFAULT '',
    hardware TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    first_heard INTEGER NOT NULL,
    last_heard INTEGER NOT NULL,
    radio_heard INTEGER,
    radio_listed INTEGER,
    packet_heard INTEGER,
    snr REAL,
    rssi REAL,
    hops INTEGER,
    battery INTEGER,
    latitude REAL,
    longitude REAL
);
CREATE INDEX IF NOT EXISTS nodes_last_heard ON nodes(last_heard);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""
COLUMNS = ('id', 'short', 'long', 'hardware', 'role', 'first_heard', 'last_heard', 'radio_heard',
           'radio_listed', 'packet_heard', 'snr', 'rssi', 'hops', 'battery', 'latitude', 'longitude')
SOURCES = ('all', 'radio', 'packets')
LIST_GRACE = 150  # the server merges the radio list every 60 s; allow for a slow merge
RESERVED = (0, 0xFFFFFFFF)


def peer_id(value):
    """'!1234abcd' for a node number or id string; None for anything else or a reserved id."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str):
        match = NODE_ID.fullmatch(value.strip())
        if not match:
            return None
        number = int(match.group(1), 16)
    else:
        return None
    if not 0 <= number <= 0xFFFFFFFF or number in RESERVED:
        return None
    return f'!{number:08x}'


def _number(value, kind=float):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = kind(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if isinstance(result, float) and not math.isfinite(result):
        return None
    return result


def _text(value, limit):
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ''
    return ''.join(c for c in str(value) if c.isprintable())[:limit].strip()


def _position(position):
    position = position if isinstance(position, dict) else {}
    out = []
    for key, bound in (('latitude', 90), ('longitude', 180)):
        value = _number(position.get(key))
        if value is None and position.get(key + 'I') is not None:
            value = _number(position.get(key + 'I'))
            value = value / 1e7 if value is not None else None
        # 0,0 is what radios report when they have no fix.
        out.append(value if value is not None and -bound <= value <= bound else None)
    if out[0] == 0 and out[1] == 0:
        return None, None
    return out[0], out[1]


def radio_row(node, now):
    """Directory fields from one entry of the radio's node list, or None without a usable id."""
    if not isinstance(node, dict):
        return None
    user = node.get('user') if isinstance(node.get('user'), dict) else {}
    identity = peer_id(user.get('id')) or peer_id(node.get('num'))
    if identity is None:
        return None
    heard = _number(node.get('lastHeard'), int)
    heard = heard if heard and 0 < heard <= now + 300 else None
    metrics = node.get('deviceMetrics') if isinstance(node.get('deviceMetrics'), dict) else {}
    battery = _number(metrics.get('batteryLevel'), int)
    hops = _number(node.get('hopsAway'), int)
    latitude, longitude = _position(node.get('position'))
    return {'id': identity, 'short': _text(user.get('shortName'), 8), 'long': _text(user.get('longName'), 40),
            'hardware': _text(user.get('hwModel'), 32), 'role': _text(user.get('role'), 24),
            'heard': heard, 'snr': _number(node.get('snr')),
            'hops': hops if hops is not None and 0 <= hops <= 7 else None,
            'battery': battery if battery is not None and 0 <= battery <= 101 else None,
            'latitude': latitude, 'longitude': longitude}


def packet_row(packet):
    """Directory fields from one received packet, or None when its sender is unusable."""
    if not isinstance(packet, dict):
        return None
    identity = peer_id(packet.get('fromId')) or peer_id(packet.get('from'))
    if identity is None:
        return None
    decoded = packet.get('decoded') if isinstance(packet.get('decoded'), dict) else {}
    user = decoded.get('user') if isinstance(decoded.get('user'), dict) else {}
    start, limit = _number(packet.get('hopStart'), int), _number(packet.get('hopLimit'), int)
    hops = start - limit if start is not None and limit is not None and 0 <= limit <= start <= 7 else None
    return {'id': identity, 'short': _text(user.get('shortName'), 8), 'long': _text(user.get('longName'), 40),
            'hardware': _text(user.get('hwModel'), 32), 'role': _text(user.get('role'), 24),
            'snr': _number(packet.get('rxSnr')), 'rssi': _number(packet.get('rxRssi')), 'hops': hops}


class NodeDirectory:
    """Every node the radio list or a received packet has told us about, kept between restarts."""

    def __init__(self, path, clock=time.time, limit=MAX_NODES):
        self.path, self.clock, self.limit = str(path), clock, limit
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
        try:
            Path(self.path).chmod(0o600)
        except OSError:
            pass

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute('PRAGMA journal_mode=WAL')
            with db:
                yield db
        finally:
            db.close()

    def record_radio(self, nodes, own_id=None):
        """Merge the radio's node list. Names always refresh; signal/position only from a newer report."""
        now = int(self.clock())
        own = peer_id(own_id)
        changed = 0
        with self.connect() as db:
            for raw in nodes or []:
                row = radio_row(raw, now)
                if row is None or row['id'] == own:
                    continue
                heard = row['heard']
                existing = db.execute('SELECT radio_heard FROM nodes WHERE id = ?', (row['id'],)).fetchone()
                if existing is None:
                    stamp = heard or now
                    db.execute(
                        'INSERT INTO nodes (id, short, long, hardware, role, first_heard, last_heard, radio_heard, '
                        'radio_listed, snr, hops, battery, latitude, longitude) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (row['id'], row['short'], row['long'], row['hardware'], row['role'], stamp, stamp, heard,
                         now, row['snr'], row['hops'], row['battery'], row['latitude'], row['longitude']))
                    changed += 1
                    continue
                self._names(db, row)
                db.execute('UPDATE nodes SET radio_listed = ? WHERE id = ?', (now, row['id']))
                if heard is not None and heard > (existing[0] or 0):
                    db.execute(
                        'UPDATE nodes SET radio_heard = ?, last_heard = MAX(last_heard, ?), snr = COALESCE(?, snr), '
                        'hops = COALESCE(?, hops), battery = COALESCE(?, battery), '
                        'latitude = COALESCE(?, latitude), longitude = COALESCE(?, longitude) WHERE id = ?',
                        (heard, heard, row['snr'], row['hops'], row['battery'], row['latitude'], row['longitude'],
                         row['id']))
                changed += 1
            self._prune(db)
        return changed

    def record_packet(self, packet, own_id=None):
        """Note a packet this Mac received. Returns True when it was recorded."""
        row = packet_row(packet)
        if row is None or row['id'] == peer_id(own_id):
            return False
        now = int(self.clock())
        with self.connect() as db:
            db.execute(
                'INSERT INTO nodes (id, short, long, hardware, role, first_heard, last_heard, packet_heard, '
                'snr, rssi, hops) VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET '
                'last_heard = MAX(last_heard, excluded.last_heard), packet_heard = excluded.packet_heard, '
                'snr = excluded.snr, rssi = excluded.rssi, hops = COALESCE(excluded.hops, hops)',
                (row['id'], row['short'], row['long'], row['hardware'], row['role'], now, now, now,
                 row['snr'], row['rssi'], row['hops']))
            self._names(db, row)
            self._prune(db)
        return True

    def import_legacy(self, rows):
        """One-time copy of the older per-packet 'nodes' table so earlier history is not lost."""
        with self.connect() as db:
            if db.execute("SELECT 1 FROM meta WHERE key = 'legacy_imported'").fetchone():
                return 0
            count = 0
            for old in rows or []:
                identity = peer_id(old.get('id')) if isinstance(old, dict) else None
                seen = _number(old.get('seen'), int) if identity else None
                if not identity or not seen or seen <= 0:
                    continue
                db.execute(
                    'INSERT INTO nodes (id, long, first_heard, last_heard, packet_heard, snr, rssi) '
                    'VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING',
                    (identity, _text(old.get('name'), 40), seen, seen, seen,
                     _number(old.get('snr')), _number(old.get('rssi'))))
                count += 1
            db.execute("INSERT INTO meta VALUES ('legacy_imported', ?)", (str(int(self.clock())),))
            self._prune(db)
        return count

    @staticmethod
    def _names(db, row):
        db.execute(
            "UPDATE nodes SET short = CASE WHEN ? != '' THEN ? ELSE short END, "
            "long = CASE WHEN ? != '' THEN ? ELSE long END, "
            "hardware = CASE WHEN ? != '' THEN ? ELSE hardware END, "
            "role = CASE WHEN ? != '' THEN ? ELSE role END WHERE id = ?",
            (row['short'], row['short'], row['long'], row['long'], row['hardware'], row['hardware'],
             row['role'], row['role'], row['id']))

    def _prune(self, db):
        count = db.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]
        if count > self.limit:
            db.execute('DELETE FROM nodes WHERE id IN (SELECT id FROM nodes ORDER BY last_heard ASC LIMIT ?)',
                       (count - self.limit,))

    def count(self):
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM nodes').fetchone()[0]

    def search(self, query='', since=None, source='all', limit=500):
        """(total matches, newest-first rows) for a name/id search, heard since a time, from a source."""
        clauses, params = [], []
        text = (query or '').strip()
        if text:
            like = '%' + text.casefold().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            match = "(lower(short) LIKE ? ESCAPE '\\' OR lower(long) LIKE ? ESCAPE '\\' OR id LIKE ? ESCAPE '\\')"
            identity = peer_id(text) if text.startswith('!') or len(text) == 8 else None
            if identity:
                clauses.append(f'(id = ? OR {match[1:-1]})')
                params.append(identity)
            else:
                clauses.append(match)
            params += [like, like, like]
        if since is not None:
            clauses.append('last_heard >= ?')
            params.append(int(since))
        if source == 'radio':
            clauses.append('radio_listed IS NOT NULL')
        elif source == 'packets':
            clauses.append('packet_heard IS NOT NULL')
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        with self.connect() as db:
            total = db.execute('SELECT COUNT(*) FROM nodes' + where, params).fetchone()[0]
            rows = db.execute(f"SELECT {', '.join(COLUMNS)} FROM nodes{where} ORDER BY last_heard DESC LIMIT ?",
                              params + [int(limit)]).fetchall()
        return total, [dict(zip(COLUMNS, row)) for row in rows]

    def radio_list_time(self):
        """When the radio's node list was last merged, or None."""
        with self.connect() as db:
            return db.execute('SELECT MAX(radio_listed) FROM nodes').fetchone()[0]

    def in_radio_list(self):
        """How many saved nodes were in the radio's most recent node list."""
        latest = self.radio_list_time()
        if latest is None:
            return 0
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM nodes WHERE radio_listed >= ?',
                              (latest - LIST_GRACE,)).fetchone()[0]


def display_name(row):
    short, long = row.get('short') or '', row.get('long') or ''
    if short and long and short != long:
        return f'{long} ({short})'
    return long or short or 'Unnamed'


def heard_via(row, latest_list=None):
    """Where this node has been heard, in plain words."""
    parts = []
    listed = row.get('radio_listed')
    if listed and latest_list is not None and listed >= latest_list - LIST_GRACE:
        parts.append('In radio list')
    elif listed:
        parts.append('Dropped by radio')
    if row.get('packet_heard'):
        parts.append('Heard by this Mac')
    return ' · '.join(parts) or 'Unknown'


def details(row):
    """Short secondary facts for one node: hardware, battery, hops, position."""
    hops = row.get('hops')
    values = (
        row.get('hardware') or None,
        row.get('role') or None,
        f"{row['battery']}% battery" if row.get('battery') is not None else None,
        f"{hops} hop{'s' if hops != 1 else ''}" if hops is not None else None,
        f"{row['latitude']:.4f}, {row['longitude']:.4f}"
        if row.get('latitude') is not None and row.get('longitude') is not None else None,
    )
    return ' · '.join(v for v in values if v)


def count_label(total, radio_count):
    """Dashboard wording: 'Known nodes: N (radio holds M)', the suffix only when the app knows more."""
    total = max(total, radio_count or 0)
    suffix = f' (radio holds {radio_count})' if radio_count is not None and total > radio_count else ''
    return f'Known nodes: {total}{suffix}'
