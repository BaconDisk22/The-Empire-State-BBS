"""Process supervision and log parsing for the Sitdown desktop.

This supervises the BBS *process*, not the radio link. A running process is
not proof of a successful radio connection.
"""
import queue
import re
import subprocess
import threading
import time

NODE_PATTERN = re.compile(r"Received message from user '([^']+)' \((![0-9a-fA-F]+)\)")
READY_PATTERN = re.compile(r"(?:BBS is running on|TC²-BBS is running on)", re.I)


class ServerSupervisor:
    def __init__(self, command, cwd, factory=None):
        self.command = list(command)
        self.cwd = str(cwd)
        self.factory = factory or subprocess.Popen
        self.events = queue.Queue()
        self.process = None
        self.started_at = None
        self.nodes = {}
        self.ready = False
        self.stopping = False

    def start(self):
        if self.process and self.process.poll() is None:
            return False
        self.stopping = False
        self.ready = False
        self.process = self.factory(
            self.command, cwd=self.cwd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.started_at = time.monotonic()
        threading.Thread(target=self._read_output, args=(self.process,), daemon=True).start()
        self.events.put(("state", "Starting BBS process..."))
        return True

    def _read_output(self, process):
        try:
            for raw in process.stdout:
                line = raw.rstrip("\r\n")
                if READY_PATTERN.search(line):
                    self.ready = True
                    self.events.put(("state", "Server initialized (radio link unverified)"))
                match = NODE_PATTERN.search(line)
                if match:
                    name, node_id = match.groups()
                    self.nodes[node_id] = (name, time.time())
                    self.events.put(("node", node_id))
                self.events.put(("log", line))
        except (OSError, ValueError) as exc:
            self.events.put(("log", f"Log reader stopped: {exc}"))
        finally:
            self.events.put(("reader_done", None))

    def uptime_seconds(self):
        return int(time.monotonic() - self.started_at) if self.started_at is not None and self.running else 0

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def stop(self):
        self.stopping = True
        process = self.process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        self.process = None
        self.started_at = None
        self.ready = False

    def poll_events(self, limit=100):
        items = []
        for _ in range(limit):
            try:
                items.append(self.events.get_nowait())
            except queue.Empty:
                break
        return items
