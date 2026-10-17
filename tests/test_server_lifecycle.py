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
             patch.object(server, 'pub') as pub, \
             patch('tcp_health.ProtocolWatchdog', return_value=watchdog):
            self.assertEqual(server.main(), 2)
        connect.assert_called_once()
        interface.close.assert_called_once()
        watchdog.close.assert_called_once()
        client.close.assert_called_once()
        pub.unsubscribe.assert_called_once()
