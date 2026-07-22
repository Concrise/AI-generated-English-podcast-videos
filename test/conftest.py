"""Safety guardrails for the default offline test suite."""

import ipaddress
import socket

import pytest


def _is_loopback_host(host: object) -> bool:
    host_text = str(host).strip().lower()
    if host_text in {"localhost", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host_text).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def block_external_network_for_unit_tests(request, monkeypatch):
    """Reject accidental paid/external requests outside integration tests."""
    if request.node.get_closest_marker("integration"):
        return

    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def guarded_connect(socket_instance, address):
        host = address[0] if isinstance(address, tuple) and address else address
        if not _is_loopback_host(host):
            raise RuntimeError(f"external network access is disabled in unit tests: {host}")
        return original_connect(socket_instance, address)

    def guarded_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) and address else address
        if not _is_loopback_host(host):
            raise RuntimeError(f"external network access is disabled in unit tests: {host}")
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
