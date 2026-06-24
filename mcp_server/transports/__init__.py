"""Transport layer — protocol adapters for device connections.

Supported protocols:
    SSH (ssh.py)       — Linux device primary channel, SCP file transfer
    Telnet (telnet.py) — Serial servers, switches, bootloader consoles
    Serial (serial.py) — Direct COM port / USB-TTL connections
"""
from .base import BaseTransport, TransportConfig, ExecResult
from .ssh import SSHTransport
from .telnet import TelnetTransport
from .serial import SerialTransport
