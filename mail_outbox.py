"""Local-only Grapevine outbox state. No radio transmission happens in this module.

A queued record is never automatically retried on TCP reconnect. A future
server-side sender must obtain explicit operator confirmation, serialize sends,
and reconcile ambiguous acknowledgements before changing delivery state.
"""
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from datetime import datetime, timezone

NODE_ID = re.compile(r"^![0-9a-fA-F]{8}$")
STATES = frozenset({"draft", "queued", "sending", "sent", "acknowledged", "failed", "unknown"})
TRANSITIONS = {
    "draft": frozenset({"queued"}),
    "queued": frozenset({"sending", "failed"}),
    "sending": frozenset({"sent", "acknowledged", "failed", "unknown"}),
    "sent": frozenset({"acknowledged", "failed", "unknown"}),
    "acknowledged": frozenset(),
    "failed": frozenset(),
    "unknown": frozenset(),
}


def validate_message(recipient, subject, body):
    recipient = recipient.strip()
    if not NODE_ID.fullmatch(recipient):
        raise ValueError("Recipient must be a Meshtastic node ID like !1234abcd")
    if not isinstance(subject, str) or not isinstance(body, str):
        raise ValueError("Subject and message must be text")
    if not subject.strip() or not body.strip():
        raise ValueError("Subject and message are required")
    if len(subject) > 120 or len(body) > 4000:
        raise ValueError("Message is too long")
    if any(ord(c) < 32 and c not in "\n\t" for c in subject + body):
        raise ValueError("Control characters are not permitted")
    return recipient.lower()


class LocalOutbox:
    """Atomic local persistence; intentionally no send method."""

    def __init__(self, folder):
        self.folder = Path(folder)

    def _path(self, message_id):
        if not re.fullmatch(r"[0-9a-f]{32}", message_id):
            raise ValueError("Invalid message ID")
        return self.folder / (message_id + ".json")

    def _save(self, record):
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self._path(record["id"])
        fd, temporary = tempfile.mkstemp(prefix=".outbox-", dir=self.folder)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(record, stream, ensure_ascii=False, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return record

    def create(self, recipient, subject, body):
        recipient = validate_message(recipient, subject, body)
        record = {
            "id": uuid.uuid4().hex,
            "recipient": recipient,
            "subject": subject.strip(),
            "body": body.strip(),
            "status": "draft",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "history": [],
            "radio_message_id": None,
        }
        return self._save(record)

    def load(self, message_id):
        with self._path(message_id).open(encoding="utf-8") as stream:
            record = json.load(stream)
        if record.get("id") != message_id or record.get("status") not in STATES:
            raise ValueError("Invalid outbox record")
        return record

    def transition(self, message_id, new_status, note=""):
        record = self.load(message_id)
        old_status = record["status"]
        if new_status not in TRANSITIONS[old_status]:
            raise ValueError("Invalid status transition; do not silently retry or resend")
        record["status"] = new_status
        record["history"].append({
            "from": old_status,
            "to": new_status,
            "at": datetime.now(timezone.utc).isoformat(),
            "note": str(note)[:300],
        })
        return self._save(record)
