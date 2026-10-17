"""Single-owner TCP session and local protocol watchdog (Meshtastic 2.7.11).

No second socket, broadcast, or inference from mesh traffic silence. Recovery
belongs to the desktop supervisor, never the library's reader/writer threads.
"""
import socket
import threading
import time

from meshtastic.tcp_interface import TCPInterface
from meshtastic.protobuf import admin_pb2, portnums_pb2


class ManagedTCPInterface(TCPInterface):
    def __init__(self, hostname):
        self.transport_failed = threading.Event()
        self._send_deadline = threading.local()
        self._write_lock = threading.Lock()
        super().__init__(hostname=hostname, timeout=30)

    def myConnect(self):
        self.socket = socket.create_connection((self.hostname, self.portNumber), timeout=5)

    def _sendToRadio(self, message):
        # Upstream queue-space waits are otherwise unbounded on a dead radio.
        self._send_deadline.at = time.monotonic() + 10
        try:
            return super()._sendToRadio(message)
        finally:
            self._send_deadline.at = None

    def _queueHasFreeSpace(self):
        deadline = getattr(self._send_deadline, "at", None)
        if self._wantExit or (deadline is not None and time.monotonic() >= deadline):
            raise TimeoutError("Radio send queue unavailable")
        return super()._queueHasFreeSpace()

    def _writeBytes(self, data):
        # A heartbeat and a reply can write concurrently; preserve frame boundaries.
        if not self._write_lock.acquire(timeout=5):
            raise TimeoutError("Radio writer busy")
        try:
            if self._wantExit:
                raise ConnectionError("Radio session closed")
            return super()._writeBytes(data)
        finally:
            self._write_lock.release()

    def _sendDisconnect(self):
        # TCPInterface.close has already shut down the socket. Do not drain a
        # stalled library TX queue during cleanup.
        pass

    def _reconnect(self):
        # The upstream reader and writer both call this. Neither may dial again.
        self.transport_failed.set()
        self._wantExit = True

    def _disconnected(self):
        self.transport_failed.set()
        super()._disconnected()

    def _readBytes(self, length):
        try:
            return super()._readBytes(length)
        except socket.timeout:
            # Idle TCP is normal; protocol requests have their own deadline.
            return None
        except OSError:
            self.transport_failed.set()
            raise


class ProtocolWatchdog:
    """Require a local metadata reply, not just a write, ACK, or open socket."""
    def __init__(self, interface, emit, clock=time.monotonic, interval=30, timeout=15):
        self.interface = interface
        self.emit = emit
        self.clock = clock
        self.interval = interval
        self.timeout = timeout
        self.next_probe = clock()
        self.deadline = None
        self.request_id = None
        self.reply = threading.Event()
        self.generation = 0
        self.misses = 0
        self.state = None
        self.set_state("CHECKING")

    def set_state(self, state):
        if self.state != state:
            self.state = state
            self.emit(state)

    def tick(self):
        now = self.clock()
        if self.interface.transport_failed.is_set() or not self.interface.isConnected.is_set():
            self.set_state("DISCONNECTED")
            return False
        if self.deadline is not None:
            if self.reply.is_set():
                self.misses = 0
                self.set_state("RESPONSIVE")
                self.finish_probe()
                self.next_probe = now + self.interval
            elif now >= self.deadline:
                self.misses += 1
                self.set_state("UNRESPONSIVE")
                self.finish_probe()
                self.next_probe = now + self.interval
                if self.misses >= 2:
                    return False
        if self.deadline is None and now >= self.next_probe:
            self.generation += 1
            generation = self.generation
            self.reply = threading.Event()
            reply = self.reply
            self.deadline = now + self.timeout
            local_num = self.interface.localNode.nodeNum

            def response(packet):
                if generation != self.generation or packet.get("from") != local_num:
                    return
                decoded = packet.get("decoded", {})
                if decoded.get("portnum") != "ADMIN_APP":
                    return
                message = admin_pb2.AdminMessage()
                try:
                    message.ParseFromString(decoded.get("payload", b""))
                except Exception:
                    return
                if message.HasField("get_device_metadata_response"):
                    reply.set()

            try:
                if not local_num or local_num == 0xFFFFFFFF:
                    raise ValueError("Local node identity unavailable")
                request = admin_pb2.AdminMessage(get_device_metadata_request=True)
                packet = self.interface.sendData(
                    request, destinationId=local_num,
                    portNum=portnums_pb2.PortNum.ADMIN_APP,
                    wantResponse=True, wantAck=False, onResponse=response)
                self.request_id = packet.id
            except Exception:
                self.set_state("UNRESPONSIVE")
                return False
        return True

    def finish_probe(self):
        self.generation += 1
        if self.request_id is not None:
            self.interface.responseHandlers.pop(self.request_id, None)
        self.request_id = None
        self.deadline = None

    def close(self):
        self.finish_probe()
