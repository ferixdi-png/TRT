import socket

import pytest


def test_network_calls_are_blocked():
    with pytest.raises(RuntimeError, match="NETWORK_DISABLED_IN_TESTS"):
        socket.create_connection(("example.com", 80), timeout=1)

    with pytest.raises(RuntimeError, match="NETWORK_DISABLED_IN_TESTS"):
        sock = socket.socket()
        try:
            sock.connect_ex(("example.com", 80))
        finally:
            sock.close()
