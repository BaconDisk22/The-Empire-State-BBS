"""The Sitdown BBS: short, radio-friendly slash command shortcuts.

These commands only act on *exact* matches, so ordinary mail and bulletin
contents (including text beginning with a slash) remain unchanged.
"""

SHORTCUTS = {
    "/sitdown": "x",
    "/menu": "x",
    "/cancel": "x",
    "/help": "q",
    "/ayyy": "q",
    "/mail": "cm",
    "/inbox": "cm",
    "/fortune": "f",
    "/boards": "b",
    "/socialclub": "b",
    "/tools": "u",
    "/utilities": "u",
}


def resolve_shortcut(message, state=None):
    """Return the mapped legacy command or None.

    Board and utility shortcuts navigate via existing menus instead of
    inventing unsupported radio commands. A pending free-text input is not
    rewritten except for explicit navigation and help shortcuts.
    """
    key = message.strip().casefold()
    command = SHORTCUTS.get(key)
    if command is None:
        return None
    state_command = (state or {}).get("command")
    if state_command in {"BULLETIN_POST", "BULLETIN_POST_CONTENT", "MAIL", "BULLETIN_READ"}:
        if key not in {"/sitdown", "/menu", "/cancel", "/help"}:
            return None
    return command
