"""Conservative radio health indicators based on observable state."""


def radio_health_label(demo, running, initialized, usb_present=None, waiting=False, tcp_state=None):
    if demo:
        return "Radio health: DEMO — no radio"
    # Waiting for an unplugged serial radio: the BBS is stopped on purpose.
    if waiting:
        return "Radio health: USB MISSING — reconnect required"
    if not running:
        return "Radio health: BBS STOPPED"
    # A TCP session must not be labelled USB MISSING because of stale USB state.
    if tcp_state:
        return f"Radio health: {tcp_state} — local protocol only; RF delivery UNVERIFIED"
    if usb_present is False:
        return "Radio health: USB MISSING — reconnect required"
    if not initialized:
        return "Radio health: STARTING — radio unverified"
    return "Radio health: BBS READY — radio link UNVERIFIED"
