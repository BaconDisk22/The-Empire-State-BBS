"""The app's own node list, kept beyond the radio's ~100-node limit."""
import io
import os
import sqlite3
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import empire_nodedir as nd
from desktop_views import nodes_summary
from sitdown_monitor import ServerSupervisor

with patch.dict(sys.modules, {"js8call_integration": Mock(), "message_processing": Mock()}):
    import server

GUI = os.environ.get("EMPIRE_GUI_TESTS") == "1"


def radio_node(number, short='', long='', heard=None, snr=None, **extra):
    node = {'num': number, 'user': {'id': f'!{number:08x}', 'shortName': short, 'longName': long}}
    if heard is not None:
        node['lastHeard'] = heard
    if snr is not None:
        node['snr'] = snr
    node.update(extra)
    return node


class Clock:
    def __init__(self, now=1_800_000_000):
        self.now = now

    def __call__(self):
        return self.now


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'node-directory.db'
        self.clock = Clock()
        self.directory = nd.NodeDirectory(self.path, clock=self.clock)

    def test_nodes_the_radio_forgets_are_kept(self):
        now = self.clock.now
        first = [radio_node(n, f'N{n}', f'Node {n}', heard=now - n) for n in range(1, 101)]
        self.directory.record_radio(first)
        self.clock.now += 300
        # The radio is full: 50 new nodes push the 50 oldest out of its list.
        second = first[:50] + [radio_node(n, f'N{n}', heard=self.clock.now) for n in range(101, 151)]
        self.directory.record_radio(second)
        self.assertEqual(self.directory.count(), 150)
        total, rows = self.directory.search('Node 99')
        self.assertEqual(total, 1)
        self.assertEqual(nd.heard_via(rows[0], self.directory.radio_list_time()), 'Dropped by radio')
        self.assertEqual(self.directory.in_radio_list(), 100)

    def test_signal_and_position_update_only_from_a_newer_report(self):
        now = self.clock.now
        self.directory.record_radio([radio_node(5, 'OLD', heard=now - 60, snr=4.0, hopsAway=1,
                                                position={'latitudeI': 427000000, 'longitudeI': -737000000})])
        self.directory.record_radio([radio_node(5, 'NEW', heard=now - 600, snr=-9.0, hopsAway=3)])
        row = self.directory.search('!00000005')[1][0]
        self.assertEqual(row['short'], 'NEW', 'names always refresh')
        self.assertEqual(row['snr'], 4.0)
        self.assertEqual(row['hops'], 1)
        self.assertAlmostEqual(row['latitude'], 42.7)
        self.directory.record_radio([radio_node(5, heard=now - 10, snr=1.5)])
        row = self.directory.search('!00000005')[1][0]
        self.assertEqual(row['snr'], 1.5)
        self.assertEqual(row['short'], 'NEW', 'an empty name never erases a known one')
        self.assertAlmostEqual(row['longitude'], -73.7, msg='a missing position keeps the last one')

    def test_received_packets_are_recorded_without_message_text(self):
        packet = {'from': 0x1234abcd, 'rxSnr': 6.25, 'rxRssi': -90, 'hopStart': 3, 'hopLimit': 1,
                  'decoded': {'text': 'private hello', 'user': {'shortName': 'ALB', 'longName': 'Albany'}}}
        self.assertTrue(self.directory.record_packet(packet))
        row = self.directory.search('alb')[1][0]
        self.assertEqual((row['id'], row['short'], row['long'], row['snr'], row['rssi'], row['hops']),
                         ('!1234abcd', 'ALB', 'Albany', 6.25, -90, 2))
        self.assertEqual(row['packet_heard'], self.clock.now)
        with sqlite3.connect(self.path) as db:
            dump = '\n'.join(db.iterdump())
        self.assertNotIn('private hello', dump)

    def test_bad_values_and_reserved_ids_are_rejected(self):
        for packet in (None, 'x', {}, {'from': 0}, {'from': 0xFFFFFFFF}, {'fromId': '!ffffffff'},
                       {'from': True}, {'fromId': 'not-a-node'}, {'from': -1}, {'from': 2 ** 40}):
            self.assertFalse(self.directory.record_packet(packet), packet)
        self.directory.record_radio([None, 'x', {'num': 0}, {'user': 'bad'},
                                     radio_node(7, 'X' * 30, '\x00bad\nname', heard=self.clock.now + 9999,
                                                snr=float('nan'), hopsAway=99,
                                                deviceMetrics={'batteryLevel': 500},
                                                position={'latitude': 0, 'longitude': 0})])
        self.assertEqual(self.directory.count(), 1)
        row = self.directory.search()[1][0]
        self.assertEqual(row['short'], 'X' * 8)
        self.assertEqual(row['long'], 'badname')
        self.assertIsNone(row['radio_heard'], 'a lastHeard far in the future is ignored')
        for key in ('snr', 'hops', 'battery', 'latitude', 'longitude'):
            self.assertIsNone(row[key], key)

    def test_own_radio_is_not_listed(self):
        self.directory.record_radio([radio_node(1, 'ME'), radio_node(2, 'YOU')], own_id='!00000001')
        self.assertFalse(self.directory.record_packet({'from': 1}, own_id='!00000001'))
        self.assertEqual([r['id'] for r in self.directory.search()[1]], ['!00000002'])

    def test_filters_by_time_source_and_search(self):
        now = self.clock.now
        self.directory.record_radio([radio_node(1, 'OLD', 'Old Timer', heard=now - 10 * 86400),
                                     radio_node(2, 'DAY', 'Day Old', heard=now - 7200)])
        self.directory.record_packet({'from': 3, 'decoded': {'user': {'shortName': 'P_1', 'longName': '100% Pkt'}}})
        self.assertEqual(self.directory.search(since=now - 3600)[0], 1)
        self.assertEqual(self.directory.search(since=now - 86400)[0], 2)
        self.assertEqual(self.directory.search()[0], 3)
        self.assertEqual({r['id'] for r in self.directory.search(source='radio')[1]}, {'!00000001', '!00000002'})
        self.assertEqual([r['id'] for r in self.directory.search(source='packets')[1]], ['!00000003'])
        self.assertEqual([r['id'] for r in self.directory.search()[1]], ['!00000003', '!00000002', '!00000001'],
                         'newest first')
        # % and _ are matched literally, not as wildcards.
        self.assertEqual(self.directory.search('100%')[0], 1)
        self.assertEqual(self.directory.search('p_1')[0], 1)
        self.assertEqual(self.directory.search('%')[0], 1)
        self.assertEqual(self.directory.search('_')[0], 1)
        self.assertEqual(self.directory.search('00000002')[0], 1)
        self.assertEqual(self.directory.search('!00000001')[0], 1)
        self.assertEqual(self.directory.search('timer')[0], 1)
        total, rows = self.directory.search(limit=2)
        self.assertEqual((total, len(rows)), (3, 2))

    def test_size_is_bounded_by_dropping_the_longest_unheard(self):
        small = nd.NodeDirectory(Path(self.temp.name) / 'small.db', clock=self.clock, limit=5)
        small.record_radio([radio_node(n, heard=self.clock.now - 1000 + n) for n in range(1, 9)])
        self.assertEqual(small.count(), 5)
        self.assertEqual({r['id'] for r in small.search()[1]}, {f'!{n:08x}' for n in range(4, 9)})

    def test_survives_restart_and_is_private(self):
        self.directory.record_radio([radio_node(9, 'KEEP')])
        reopened = nd.NodeDirectory(self.path, clock=self.clock)
        self.assertEqual(reopened.search('keep')[0], 1)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_older_history_is_imported_once(self):
        legacy = [{'id': '!0000000a', 'name': 'Legacy', 'seen': 1_700_000_000.5, 'snr': 1.0, 'rssi': -80},
                  {'id': 'bad', 'name': 'x', 'seen': 5}, {'id': '!0000000b', 'name': 'NoTime', 'seen': None}]
        self.assertEqual(self.directory.import_legacy(legacy), 1)
        self.assertEqual(self.directory.import_legacy(legacy + [{'id': '!0000000c', 'seen': 9}]), 0)
        row = self.directory.search('legacy')[1][0]
        self.assertEqual((row['last_heard'], row['packet_heard'], row['rssi']), (1_700_000_000, 1_700_000_000, -80))

    def test_two_connections_see_each_others_writes(self):
        reader = nd.NodeDirectory(self.path, clock=self.clock)
        self.directory.record_packet({'from': 42})
        self.assertEqual(reader.count(), 1)


class FormattingTests(unittest.TestCase):
    def test_names_sources_and_details(self):
        row = {'id': '!00000001', 'short': 'ALB', 'long': 'Albany', 'radio_listed': 1000, 'packet_heard': 990,
               'hardware': 'HELTEC_V3', 'role': 'ROUTER', 'battery': 87, 'hops': 1,
               'latitude': 42.65, 'longitude': -73.75}
        self.assertEqual(nd.display_name(row), 'Albany (ALB)')
        self.assertEqual(nd.display_name({'short': 'X', 'long': ''}), 'X')
        self.assertEqual(nd.display_name({}), 'Unnamed')
        self.assertEqual(nd.heard_via(row, 1000), 'In radio list · Heard by this Mac')
        self.assertEqual(nd.heard_via(row, 5000), 'Dropped by radio · Heard by this Mac')
        self.assertEqual(nd.heard_via({'id': 'x'}), 'Unknown')
        self.assertEqual(nd.details(row), 'HELTEC_V3 · ROUTER · 87% battery · 1 hop · 42.6500, -73.7500')
        self.assertEqual(nd.details({}), '')

    def test_dashboard_count_suffix_only_when_the_app_knows_more(self):
        self.assertEqual(nd.count_label(250, 100), 'Known nodes: 250 (radio holds 100)')
        self.assertEqual(nd.count_label(80, 80), 'Known nodes: 80')
        self.assertEqual(nd.count_label(12, None), 'Known nodes: 12')
        self.assertEqual(nd.count_label(0, 3), 'Known nodes: 3')

    def test_locals_summary_line(self):
        self.assertEqual(nodes_summary(250, 250, 250, 100),
                         '250 saved on this Mac · your radio holds 100 '
                         '(radios forget the oldest when full; this list keeps them)')
        self.assertTrue(nodes_summary(500, 900, 900, 100).startswith('Showing 500 of 900 · 900 saved'))
        self.assertTrue(nodes_summary(3, 3, 900, 100).startswith('3 match · 900 saved'))


class ServerWiringTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = nd.NodeDirectory(Path(temp.name) / 'd.db')

    def interface(self, nodes):
        return Mock(nodes={n['user']['id']: n for n in nodes}, myInfo=Mock(my_node_num=1))

    def test_sync_merges_the_radio_list_and_reports_its_size(self):
        interface = self.interface([radio_node(1, 'ME'), radio_node(2, 'A'), radio_node(3, 'B')])
        with patch('sys.stdout', new=io.StringIO()) as out:
            self.assertEqual(server.sync_radio_nodes(self.directory, interface), 2)
        self.assertEqual(out.getvalue(), 'EMPIRE_RADIO_NODES 2\n')
        self.assertEqual(self.directory.count(), 2)

    def test_sync_ignores_a_missing_list_and_database_errors(self):
        self.assertIsNone(server.sync_radio_nodes(self.directory, Mock(nodes=None)))
        broken = Mock(record_radio=Mock(side_effect=sqlite3.OperationalError('locked')))
        with patch('sys.stdout', new=io.StringIO()) as out:
            self.assertIsNone(server.sync_radio_nodes(broken, self.interface([radio_node(2)])))
        self.assertEqual(out.getvalue(), '')

    def test_directory_only_when_the_desktop_asks(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(server.open_node_directory())
        with patch.dict(os.environ, {'EMPIRE_NODE_DIRECTORY': self.directory.path}):
            self.assertIsInstance(server.open_node_directory(), nd.NodeDirectory)

    def test_own_node_id(self):
        self.assertEqual(server.own_node_id(Mock(myInfo=Mock(my_node_num=0xabc))), '!00000abc')
        self.assertIsNone(server.own_node_id(Mock(myInfo=None, localNode=None)))

    def test_supervisor_reads_the_radio_count_record_only(self):
        process = Mock(stdout=io.StringIO('x EMPIRE_RADIO_NODES 5\nEMPIRE_RADIO_NODES 100\n'))
        supervisor = ServerSupervisor(['x'], '.')
        supervisor.process = process
        supervisor._read_output(process)
        self.assertEqual(supervisor.radio_nodes, 100)
        events = []
        while not supervisor.events.empty():
            events.append(supervisor.events.get())
        self.assertIn(('radio_nodes', 100), events)
        self.assertIn(('log', 'x EMPIRE_RADIO_NODES 5'), events, 'an embedded record is just a log line')
        self.assertNotIn(('log', 'EMPIRE_RADIO_NODES 100'), events)


@unittest.skipUnless(GUI, "Set EMPIRE_GUI_TESTS=1 with a working Tk display (enabled in CI)")
class LocalsPageTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from sitdown_desktop import SitdownApp
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        data = Path(temp.name)
        for p in [patch("sitdown_desktop.DATA", data), patch("sitdown_desktop.CONFIG", data / "launcher.json"),
                  patch("sitdown_desktop.ROOT", data), patch("sitdown_desktop.ServerSupervisor")]:
            p.start()
            self.addCleanup(p.stop)
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        with patch.object(SitdownApp, "poll"):
            self.app = SitdownApp(self.root)
        self.data = data

    def test_locals_lists_every_saved_node_and_filters(self):
        import time
        now = time.time()
        self.app.node_directory.record_radio([radio_node(n, f'N{n}', heard=int(now) - n * 60 + 30) for n in range(1, 151)])
        self.app.radio_node_count = 100
        self.app.refresh_node_count()
        self.assertEqual(self.app.node_count.get(), 'Known nodes: 150 (radio holds 100)')
        self.assertTrue((self.data / 'node-directory.db').exists())
        page = self.app.page_objects['locals']
        self.app.navigate('locals')
        self.root.update_idletasks()
        self.assertEqual(len(page.listing.get_children()), 150)
        self.assertIn('150 saved on this Mac · your radio holds 100', page.count_line.cget('text'))
        page.period.set('hour')
        self.root.update_idletasks()
        self.assertEqual(len(page.listing.get_children()), 60)
        page.search.set('N7')
        self.assertEqual(len(page.listing.get_children()), 1)


if __name__ == '__main__':
    unittest.main()
