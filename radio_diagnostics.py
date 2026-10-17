"""Non-transmitting radio target checks; never claim Meshtastic connectivity."""
import socket


def available_serial_ports():
    from serial.tools import list_ports
    return [port.device for port in list_ports.comports()]


def check_serial_target(address, ports=None):
    """Enumerate serial devices; do not open or reset a radio."""
    if ports is None:
        ports = available_serial_ports()
    if not address:
        if not ports:
            return "No USB serial devices found. Check cable, permissions and radio power."
        return ("Available USB ports: " + ", ".join(ports) +
                ". Select one before starting. Radio link unverified.")
    if address not in ports:
        return (f"Selected serial port {address!r} is not currently enumerated. "
                "Reconnect the device and rescan; radio link unverified.")
    return (f"Serial port {address!r} is present. "
            "This does not verify permissions, firmware, or a Meshtastic connection.")


def check_tcp_target(host, port=4403, timeout=2.0, connector=None):
    """Test TCP reachability only; does not negotiate a Meshtastic session."""
    if not host:
        return "Enter a TCP host before testing."
    dial = connector or socket.create_connection
    try:
        sock = dial((host, port), timeout=timeout)
        sock.close()
    except (OSError, TimeoutError) as exc:
        return (f"TCP {host}:{port} unreachable: {exc}. "
                "Check radio power, network, IP address and firewall.")
    return (f"TCP {host}:{port} accepted a connection. "
            "Meshtastic protocol and message delivery remain unverified.")
