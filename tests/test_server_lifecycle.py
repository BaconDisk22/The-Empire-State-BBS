import unittest
from unittest.mock import Mock, patch
import sys

# These handlers read the operator config at import time; isolate unrelated
# integrations so lifecycle tests need no live config or database.
with patch.dict(sys.modules, {"js8call_integration": Mock(), "message_processing": Mock()}):
    import server


class ServerLifecycleTests(unittest.TestCase):
    def test_health_failure_closes_session_and_does_not_redial(self):
        config = {'interface_type': 'tcp', 'bbs_nodes': [], 'allowed_nodes': [],
                  'mqtt_topic': 'meshtastic.receive'}
        interface = Mock()
        client = Mock(db_conn=None)
        watchdog = Mock()
        watchdog.tick.return_value = False
        with patch.object(server, 'display_banner'), \
             patch.object(server, 'init_cli_parser', return_value=Mock(config=None)), \
             patch.object(server, 'initialize_config', return_value=config), \
             patch.object(server, 'merge_config'), \
             patch.object(server, 'get_interface', return_value=interface) as connect, \
             patch.object(server, 'initialize_database'), \
             patch.object(server, 'JS8CallClient', return_value=client), \
             patch.object(server.threading, 'Thread') as worker, \
             patch.object(server, 'pub') as pub, \
             patch('tcp_health.ProtocolWatchdog', return_value=watchdog):
            self.assertEqual(server.main(), 2)
        connect.assert_called_once()
        interface.close.assert_called_once()
        watchdog.close.assert_called_once()
        self.assertTrue(worker.call_args.kwargs["daemon"])
        worker.return_value.start.assert_called_once()
        pub.unsubscribe.assert_called_once()

    def test_js8_database_is_created_and_closed_in_worker(self):
        stopping = Mock(is_set=Mock(return_value=False))
        client = Mock()
        with patch.object(server, 'JS8CallClient', return_value=client):
            server.run_js8call(Mock(), stopping)
        client.connect.assert_called_once()
        client.close.assert_called_once()
        client.db_conn.close.assert_called_once()

    def test_js8_does_not_start_after_shutdown(self):
        stopping = Mock(is_set=Mock(return_value=True))
        client = Mock()
        with patch.object(server, 'JS8CallClient', return_value=client):
            server.run_js8call(Mock(), stopping)
        client.connect.assert_not_called()
        client.close.assert_called_once()
