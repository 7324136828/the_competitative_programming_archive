"""LAN discovery reports only addresses served by each listener."""

import socket
import unittest
from unittest.mock import MagicMock, patch

from backend import network


def records(addresses, family=socket.AF_INET):
    return [(family, socket.SOCK_STREAM, 0, "", (address, 0)) for address in addresses]


class NetworkTests(unittest.TestCase):
    def test_ipv4_discovery_deduplicates_filters_and_sorts_adapters(self):
        addresses = ["192.168.1.20", "10.0.0.2", "192.168.1.20", "127.0.0.1",
                     "169.254.1.2", "224.0.0.1", "0.0.0.0", "255.255.255.255"]
        with patch.object(socket, "getaddrinfo", return_value=records(addresses)):
            self.assertEqual(network.discover_lan_ipv4(), ["10.0.0.2", "192.168.1.20"])
        with patch.object(socket, "getaddrinfo", side_effect=OSError):
            self.assertEqual(network.discover_lan_ipv4(), [])

    def test_loopback_and_ipv6_addresses_never_advertise_unrelated_ipv4(self):
        for host in ("127.0.0.1", "::1", "169.254.1.2", "fe80::1"):
            self.assertEqual(network.lan_urls_for_host(host, 5173), [])
        self.assertEqual(network.lan_urls_for_host("2001:db8::1", 5173), ["http://[2001:db8::1]:5173"])
        self.assertEqual(network.lan_urls_for_host("192.168.1.20", 5173), ["http://192.168.1.20:5173"])

    def test_hostname_uses_only_resolved_lan_addresses(self):
        resolved = records(["192.168.1.20", "127.0.0.1"]) + records(["2001:db8::1"], socket.AF_INET6)
        with patch.object(socket, "getaddrinfo", return_value=resolved):
            self.assertEqual(network.lan_urls_for_host("study-pc", 5173), [
                "http://192.168.1.20:5173", "http://[2001:db8::1]:5173",
            ])

    def test_wildcard_ipv6_and_dual_stack_reflect_socket_configuration(self):
        listener = MagicMock(family=socket.AF_INET6)
        listener.getsockname.return_value = ("::", 5173, 0, 0)
        with patch.object(network, "discover_lan_ipv4", return_value=["192.168.1.20"]), patch.object(
            network, "discover_lan_ipv6", return_value=["2001:db8::1"]
        ):
            listener.getsockopt.return_value = 1
            self.assertEqual(network.lan_urls(listener), ["http://[2001:db8::1]:5173"])
            listener.getsockopt.return_value = 0
            self.assertEqual(network.lan_urls(listener), ["http://[2001:db8::1]:5173", "http://192.168.1.20:5173"])

    def test_explicit_listener_only_advertises_its_bound_address(self):
        listener = MagicMock(family=socket.AF_INET)
        listener.getsockname.return_value = ("192.168.1.20", 5173)
        with patch.object(network, "discover_lan_ipv4") as discover:
            self.assertEqual(network.lan_urls(listener), ["http://192.168.1.20:5173"])
        discover.assert_not_called()
        listener.getsockname.side_effect = OSError("closed")
        self.assertEqual(network.lan_urls(listener), [])


if __name__ == "__main__":
    unittest.main()
