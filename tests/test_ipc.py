"""Tests for the inter-process command pipe (sotto.ipc)."""

import sys
import time

import pytest

from sotto.ipc import CommandServer, send_command


@pytest.mark.skipif(sys.platform != "win32", reason="named pipes are Windows")
def test_command_round_trip():
    received: list[dict] = []
    server = CommandServer(lambda payload: received.append(payload))
    server.start()
    try:
        time.sleep(0.4)  # let the listener thread create the pipe
        assert send_command("dictate") is True
        time.sleep(0.5)
        assert received == [{"command": "dictate"}], received
    finally:
        server.stop()


@pytest.mark.skipif(sys.platform != "win32", reason="named pipes are Windows")
def test_command_with_extra_fields():
    received: list[dict] = []
    server = CommandServer(lambda payload: received.append(payload))
    server.start()
    try:
        time.sleep(0.4)
        assert send_command("show", source="jump") is True
        time.sleep(0.5)
        assert received == [{"command": "show", "source": "jump"}], received
    finally:
        server.stop()


@pytest.mark.skipif(sys.platform != "win32", reason="named pipes are Windows")
def test_send_without_server_returns_false():
    # no server listening → nothing to write to
    assert send_command("dictate") is False
