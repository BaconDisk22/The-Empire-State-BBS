"""Conservative radio health indicators based on observable state."""


def radio_health_label(demo, running, initialized, usb_present=None, waiting=False, tcp_state=None):
    if demo:
        return "Radio health: DEMO — no radio"
    if waiting or usb_present is False:
        return "Radio health: USB MISSING — reconnect required"
    if not running:
        return "Radio health: BBS STOPPED"
    if tcp_state:
        return f"Radio health: {tcp_state} — local protocol only; RF delivery UNVERIFIED"
    if not initialized:
        return "Radio health: STARTING — radio unverified"
    return "Radio health: BBS READY — radio link UNVERIFIED"
