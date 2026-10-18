"""One-shot Grapevine command protocol for a future desktop/server pipe.

The desktop must send only a validated, explicitly confirmed request.
The server owns the Meshtastic interface; never open a competing connection.
An accepted command means *attempted*, not delivered or acknowledged.
"""
import json
import re

from mail_outbox import validate_message

MAX_LINE = 8192
COMMAND = "grapevine.send"


def encode_send(message_id, recipient, subject, body):
    if not re.fullmatch(r"[0-9a-f]{32}", message_id):
        raise ValueError("Invalid outbox message ID")
    recipient = validate_message(recipient, subject, body)
    payload = {"command": COMMAND, "id": message_id,
               "recipient": recipient, "subject": subject, "body": body}
    line = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    if len(line.encode("utf-8")) > MAX_LINE:
        raise ValueError("Command exceeds transport limit")
    return line + "\n"


def decode_send(line):
    if not isinstance(line, str) or len(line.encode("utf-8")) > MAX_LINE:
        raise ValueError("Invalid command size")
    data = json.loads(line)
    if not isinstance(data, dict) or set(data) != {"command", "id", "recipient", "subject", "body"}:
        raise ValueError("Unexpected command fields")
    if data["command"] != COMMAND:
        raise ValueError("Unknown command")
    return encode_send(data["id"], data["recipient"], data["subject"], data["body"])


class SessionDeduplicator:
    """Reject duplicate IDs in one server session; persistence is still required."""

    def __init__(self):
        self._seen = set()

    def accept(self, command_line):
        validated = decode_send(command_line)
        message_id = json.loads(validated)["id"]
        if message_id in self._seen:
            raise ValueError("Duplicate send request")
        self._seen.add(message_id)
        return json.loads(validated)
