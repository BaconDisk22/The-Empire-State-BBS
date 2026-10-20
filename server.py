#!/usr/bin/env python3

"""
The Empire State BBS server for Meshtastic\nDerived from TC²-BBS by TheCommsChannel (original upstream credit retained).
Date: 07/14/2024
Version: 0.1.6

Description:
The system allows for mail message handling, bulletin boards, and a channel
directory. It uses a configuration file for setup details and an SQLite3
database for data storage. Mail messages and bulletins are synced with
other BBS servers listed in the config.ini file.
"""

import os
import sys
from desktop_session import DesktopStore, RadioSession

import logging
import time
import threading

from config_init import initialize_config, get_interface, init_cli_parser, merge_config
from db_operations import initialize_database
from js8call_integration import JS8CallClient
from message_processing import on_receive
from pubsub import pub

# General logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# JS8Call logging
js8call_logger = logging.getLogger('js8call')
js8call_logger.setLevel(logging.DEBUG)
js8call_handler = logging.StreamHandler()
js8call_handler.setLevel(logging.DEBUG)
js8call_formatter = logging.Formatter('%(asctime)s - JS8Call - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
js8call_handler.setFormatter(js8call_formatter)
js8call_logger.addHandler(js8call_handler)

def display_banner():
    banner = """
======================================
       THE EMPIRE STATE BBS
  From the Boroughs to the North Country
======================================
Meshtastic BBS Server
"""
    print(banner)

def run_js8call(interface, stopping):
    """Keep optional blocking JS8 I/O off the radio health loop.

    Construct its SQLite connection in the worker that uses it. The worker is
    daemonized so blocked external I/O cannot keep a failed radio session alive.
    """
    client = None
    try:
        client = JS8CallClient(interface)
        client.logger = js8call_logger
        if client.db_conn and not stopping.is_set():
            client.connect()
    except Exception:
        js8call_logger.exception("JS8Call integration stopped")
    finally:
        if client:
            client.close()
            if client.db_conn:
                client.db_conn.close()


def main():
    display_banner()
    args = init_cli_parser()
    config_file = None
    if args.config is not None:
        config_file = args.config
    system_config = initialize_config(config_file)

    merge_config(system_config, args)

    interface = None
    stopping = threading.Event()
    watchdog = None
    desktop = None

    def receive_packet(packet, interface):
        if desktop:
            desktop.observe(packet)
        on_receive(packet, interface)

    def health(state):
        # Dedicated, anchored supervisor record; ordinary radio logs cannot set health.
        print("EMPIRE_RADIO_HEALTH " + state, flush=True)

    try:
        if system_config['interface_type'] == 'tcp':
            health("CONNECTING")
        interface = get_interface(system_config)
        interface.bbs_nodes = system_config['bbs_nodes']
        interface.allowed_nodes = system_config['allowed_nodes']
        initialize_database()
        pub.subscribe(receive_packet, system_config['mqtt_topic'])
        threading.Thread(target=run_js8call, args=(interface, stopping),
                         daemon=True, name="JS8Call").start()
        logging.info(f"The Empire State BBS is running on {system_config['interface_type']} interface...")
        if system_config['interface_type'] == 'tcp':
            from tcp_health import ProtocolWatchdog
            watchdog = ProtocolWatchdog(interface, health)
        if os.environ.get("EMPIRE_DESKTOP_STORE"):
            desktop = RadioSession(interface, DesktopStore(os.environ["EMPIRE_DESKTOP_STORE"], "bulletins.db"),
                                   lambda: not stopping.is_set() and (watchdog is None or watchdog.state == "RESPONSIVE"))
            threading.Thread(target=desktop.read_commands, args=(sys.stdin, stopping),
                             daemon=True, name="DesktopCommands").start()
        while True:
            if watchdog and not watchdog.tick():
                logging.error("Radio session failed; stopping. Desktop recovery requires opt-in.")
                return 2
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Shutting down the server...")
        return 0
    except Exception:
        health("FAILED")
        logging.exception("BBS session failed")
        return 1
    finally:
        stopping.set()
        pub.unsubscribe(receive_packet, system_config['mqtt_topic'])
        if watchdog:
            watchdog.close()
        if interface:
            interface.close()

if __name__ == "__main__":
    raise SystemExit(main())
