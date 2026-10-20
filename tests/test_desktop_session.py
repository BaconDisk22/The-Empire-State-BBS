import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from desktop_session import DesktopStore, RadioSession


class DesktopSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DesktopStore(Path(self.temp.name) / 'desktop.db')
        self.radio = Mock()
        self.radio.sendText.return_value.id = 42
        self.session = RadioSession(self.radio, self.store)

    def draft(self, **kwargs):
        values = dict(kind='mail', subject='Hello', body='New York', recipient='!1234abcd')
        values.update(kwargs)
        return self.store.create(**values)

    def test_save_is_local_then_explicit_send_uses_existing_interface(self):
        post = self.draft()
        self.radio.sendText.assert_not_called()
        self.store.queue(post)
        self.session.send(post)
        self.radio.sendText.assert_called_once_with('Hello\nNew York', destinationId='!1234abcd', wantAck=True)
        record = self.store.get(post)
        self.assertEqual(record['state'], 'sent')
        self.assertEqual(record['packet_id'], '42')
        self.assertIn('unverified', record['detail'])

    def test_duplicate_after_restart_never_sends(self):
        post = self.draft()
        self.store.queue(post)
        self.session.send(post)
        session = RadioSession(self.radio, DesktopStore(self.store.path))
        with self.assertRaises(ValueError):
            session.send(post)
        self.assertEqual(self.radio.sendText.call_count, 1)

    def test_concurrent_duplicate_only_submits_once(self):
        post = self.draft()
        self.store.queue(post)
        errors = []
        def send():
            try:
                self.session.send(post)
            except ValueError as exc:
                errors.append(exc)
        workers = [threading.Thread(target=send) for _ in range(4)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(self.radio.sendText.call_count, 1)
        self.assertEqual(len(errors), 3)

    def test_crash_claim_becomes_unknown_without_resend(self):
        post = self.draft()
        self.store.queue(post)
        self.store.change(post, 'queued', 'sending', 'claim')
        RadioSession(self.radio, self.store)
        self.assertEqual(self.store.get(post)['state'], 'unknown')
        self.radio.sendText.assert_not_called()

    def test_failed_radio_call_is_ambiguous(self):
        self.radio.sendText.side_effect = OSError('Disconnected after write')
        post = self.draft()
        self.store.queue(post)
        self.session.send(post)
        self.assertEqual(self.store.get(post)['state'], 'unknown')
        with self.assertRaises(ValueError):
            self.session.send(post)
        self.assertEqual(self.radio.sendText.call_count, 1)

    def test_reconnect_never_drains_queued_records(self):
        post = self.draft()
        self.store.queue(post)
        RadioSession(self.radio, self.store)
        self.assertEqual(self.store.get(post)['state'], 'queued')
        self.radio.sendText.assert_not_called()

    def test_unavailable_radio_fails_before_submission(self):
        post = self.draft()
        self.store.queue(post)
        RadioSession(self.radio, self.store, available=lambda: False).send(post)
        self.assertEqual(self.store.get(post)['state'], 'failed')
        self.radio.sendText.assert_not_called()

    def test_invalid_broadcast_or_missing_recipient_cannot_transmit(self):
        for recipient in ('^all', '!ffffffff', '!00000000', '!1234', None, 123):
            with self.subTest(recipient=recipient), self.assertRaises(ValueError):
                self.draft(recipient=recipient)
        post = self.draft(recipient='')
        with self.assertRaises(ValueError):
            self.store.queue(post)
        self.radio.sendText.assert_not_called()

    def test_utf8_limit_is_bytes_and_never_truncates(self):
        post = self.draft(body='🗽' * 60)
        with self.assertRaises(ValueError):
            self.store.queue(post)
        self.assertEqual(self.store.get(post)['state'], 'draft')

    def test_local_bulletin_reply_is_persistent_and_transmits_only_explicitly(self):
        parent = self.draft(kind='bulletin', recipient='')
        reply = self.draft(kind='bulletin', parent=parent)
        reopened = DesktopStore(self.store.path)
        self.assertEqual(reopened.get(reply)['parent'], parent)
        with reopened.connect() as db:
            rows = db.execute('SELECT board,unique_id FROM bbs.bulletins').fetchall()
        self.assertEqual({row['unique_id'] for row in rows}, {parent, reply})
        self.assertTrue(all(row['board'] == 'General' for row in rows))
        self.assertEqual(reopened.get(parent)['state'], 'draft')
        self.radio.sendText.assert_not_called()
        reopened.queue(reply)
        self.session.send(reply)
        self.assertTrue(self.radio.sendText.call_args.args[0].startswith('Bulletin: Reply: '))
        self.assertEqual(reopened.get(parent)['state'], 'draft')

    def test_subject_cannot_embed_newline_or_tab(self):
        for subject in ('Hello\nworld', 'Hello\rworld', 'Hello\tworld'):
            with self.subTest(subject=subject), self.assertRaises(ValueError):
                self.draft(subject=subject)
        self.assertEqual(self.store.records('posts'), [])

    def test_mail_cannot_claim_bulletin_parent(self):
        parent = self.draft(kind='bulletin', recipient='')
        with self.assertRaises(ValueError):
            self.draft(kind='mail', parent=parent)
        self.assertEqual(len(self.store.records('posts')), 1)

    def test_missing_reply_parent_rejected(self):
        with self.assertRaises(ValueError):
            self.draft(kind='bulletin', parent='missing')

    def test_packets_deduplicate_and_only_observed_signal_is_shown(self):
        packet = {'from': 0x1234abcd, 'id': 99, 'rxSnr': 0.0, 'rxRssi': -100,
                  'decoded': {'text': 'hello', 'user': {'longName': 'Albany'}}}
        self.session.observe(packet)
        self.session.observe(packet)
        self.assertEqual(len(self.store.records('received')), 1)
        node = self.store.records('nodes')[0]
        self.assertEqual(node['snr'], 0.0)
        self.assertEqual(node['rssi'], -100)
        self.session.observe({'from': 0x1234abcd, 'decoded': {}})
        node = self.store.records('nodes')[0]
        self.assertEqual(node['name'], 'Albany')
        self.assertIsNone(node['snr'])
        self.assertIsNone(node['rssi'])
        self.radio.sendText.assert_not_called()

    def test_received_reply_is_a_persistent_local_draft_until_explicit_send(self):
        self.session.observe({'fromId': '!1234abcd', 'id': 99, 'decoded': {'text': 'Hello\nthere'}})
        received = self.store.records('received')[0]
        fields = self.store.reply_fields(received['key'])
        self.assertEqual(fields, {'recipient': '!1234abcd', 'subject': 'Re: received message'})
        self.assertEqual(self.store.records('posts'), [])
        post = self.store.create('mail', body='My reply', **fields)
        reopened = DesktopStore(self.store.path)
        self.assertEqual(reopened.get(post)['state'], 'draft')
        self.assertIsNone(reopened.get(post)['parent'])
        self.radio.sendText.assert_not_called()
        reopened.queue(post)
        self.session.send(post)
        self.radio.sendText.assert_called_once_with('Re: received message\nMy reply', destinationId='!1234abcd', wantAck=True)

    def test_reply_requires_a_received_message_with_valid_sender(self):
        with self.assertRaises(ValueError):
            self.store.reply_fields('missing')
        for sender in ('!00000000', '!ffffffff', 'invalid', None):
            with self.subTest(sender=sender):
                with self.store.connect() as db:
                    db.execute('INSERT OR REPLACE INTO received VALUES (?,?,?,?)', ('bad', sender, 'text', 1))
                with self.assertRaises(ValueError):
                    self.store.reply_fields('bad')
        self.assertEqual(self.store.records('posts'), [])
        self.radio.sendText.assert_not_called()

    def test_reserved_sender_ids_are_ignored(self):
        for sender in ('!00000000', '!ffffffff'):
            with self.subTest(sender=sender):
                self.session.observe({'fromId': sender, 'id': 7, 'decoded': {'text': 'fake'}})
        self.assertEqual(self.store.records('nodes'), [])
        self.assertEqual(self.store.records('received'), [])

    def test_same_packet_id_from_different_nodes_is_retained(self):
        for sender in (1, 2):
            self.session.observe({'from': sender, 'id': 9, 'decoded': {'text': 'same'}})
        self.assertEqual(len(self.store.records('received')), 2)

    def test_command_stream_ignores_invalid_and_duplicate_requests(self):
        post = self.draft()
        self.store.queue(post)
        command = json.dumps({'send': post}) + '\n'
        stream = io.StringIO('x' * 2048 + '\n' + '{bad}\n' + '[]\n' + command * 2)
        self.session.read_commands(stream, threading.Event())
        self.radio.sendText.assert_called_once()

    def test_stopped_session_does_not_read_commands(self):
        post = self.draft()
        self.store.queue(post)
        stopping = threading.Event()
        stopping.set()
        self.session.read_commands(io.StringIO(json.dumps({'send': post}) + '\n'), stopping)
        self.radio.sendText.assert_not_called()


if __name__ == '__main__':
    unittest.main()

class DesktopPipeTests(unittest.TestCase):
    def test_supervisor_sends_only_on_explicit_ready_session(self):
        from sitdown_monitor import ServerSupervisor
        supervisor = ServerSupervisor(['unused'], '.')
        with self.assertRaises(ValueError):
            supervisor.send_desktop('a' * 32)
        supervisor.process = Mock()
        supervisor.process.poll.return_value = None
        supervisor.process.stdin = io.StringIO()
        with self.assertRaises(ValueError):
            supervisor.send_desktop('a' * 32)
        supervisor.ready = True
        supervisor.send_desktop('a' * 32)
        self.assertEqual(json.loads(supervisor.process.stdin.getvalue()), {'send': 'a' * 32})
        supervisor.stopping = True
        with self.assertRaises(ValueError):
            supervisor.send_desktop('b' * 32)
